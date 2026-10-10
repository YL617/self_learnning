"""M4 题库闭环测试：管理员建题/绑定/覆盖 + 共享可见性 + DB 级 container 禁令。

关键路径覆盖（docs/M4设计方案.md §7）：
  1. 权限：普通用户不能管理题目；管理员可以。
  2. container 拒绝：服务层 400 + DB 层复合外键 IntegrityError（双保险）。
  3. visibility：shared 题其他用户可见可答；他人私题仍 404。
  4. 数据：shared 题作答 → AnswerRecord 正确生成 + mastery 更新。
  5. 隔离：知识点反查不被他人私题污染；导入功能回归由 test_knowledge_import 全量保证。
  6. 覆盖统计：concept 口径正确、container 不计入。
"""

import itertools

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.core.database import Base, SessionLocal
from app.models import (
    AnswerRecord,
    KnowledgePoint,
    Question,
    QuestionKnowledgePoint,
    User,
    UserKnowledgePointMastery,
)


@pytest.fixture(autouse=True)
def _clean_m4_tables():
    with SessionLocal() as db:
        db.execute(delete(UserKnowledgePointMastery))
        db.execute(delete(AnswerRecord))
        db.execute(delete(QuestionKnowledgePoint))
        db.execute(delete(Question))
        db.execute(delete(KnowledgePoint))
        db.commit()
    yield
    with SessionLocal() as db:
        db.execute(delete(UserKnowledgePointMastery))
        db.execute(delete(AnswerRecord))
        db.execute(delete(QuestionKnowledgePoint))
        db.execute(delete(Question))
        db.execute(delete(KnowledgePoint))
        db.commit()


_EMAIL_SEQ = itertools.count()


def _register(client, email: str, username: str) -> dict:
    local, _, domain = email.partition("@")
    seq = next(_EMAIL_SEQ)
    unique_email = f"{local}.{seq}@{domain}"
    unique_name = f"{username}{seq}"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": unique_email, "username": unique_name, "password": "123456"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(auth: dict) -> dict:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _set_role(auth: dict, role: str) -> None:
    with SessionLocal() as db:
        user = db.get(User, auth["user"]["id"])
        user.role = role
        db.commit()


def _make_kp(name: str, subject: str = "数据结构", node_type: str = "concept") -> int:
    with SessionLocal() as db:
        kp = KnowledgePoint(
            name=name,
            normalized_name=name.lower(),
            subject=subject,
            normalized_subject=subject.lower(),
            node_type=node_type,
        )
        db.add(kp)
        db.commit()
        return kp.id


def _admin(client) -> dict:
    auth = _register(client, "m4admin@test.com", "m4admin")
    _set_role(auth, "admin")
    return auth


def _make_private_question(user_id: int, subject: str = "数据结构") -> int:
    with SessionLocal() as db:
        question = Question(
            user_id=user_id,
            subject=subject,
            knowledge_point="栈",
            question_type="choice",
            stem="私题：栈的特点？",
            answer="B",
            source="ai",
            visibility="private",
        )
        db.add(question)
        db.commit()
        return question.id


def _create_question(client, headers, **overrides) -> dict:
    payload = {
        "subject": "数据结构",
        "knowledge_point": "栈",
        "question_type": "choice",
        "stem": "栈的操作特点是？",
        "options": ["A. 先进先出", "B. 后进先出", "C. 随机访问", "D. 双端进出"],
        "answer": "B",
        "analysis": "栈是后进先出（LIFO）结构。",
        "difficulty": "easy",
        "visibility": "shared",
    }
    payload.update(overrides)
    response = client.post("/api/v1/admin/questions", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ---------- 1. 权限 ----------


def test_regular_user_cannot_manage_questions(client):
    user = _register(client, "m4user1@test.com", "m4user1")
    kp_id = _make_kp("栈")
    # 创建
    response = client.post(
        "/api/v1/admin/questions",
        headers=_headers(user),
        json={"subject": "数据结构", "knowledge_point": "栈", "stem": "s", "answer": "a"},
    )
    assert response.status_code == 403
    # 绑定
    response = client.post(
        "/api/v1/admin/questions/1/knowledge-points",
        headers=_headers(user),
        json={"knowledge_point_id": kp_id},
    )
    assert response.status_code == 403
    # 详情
    assert client.get("/api/v1/admin/questions/1", headers=_headers(user)).status_code == 403
    # 覆盖统计
    assert (
        client.get("/api/v1/admin/knowledge-coverage", headers=_headers(user)).status_code
        == 403
    )


def test_admin_can_create_question_with_kp_binding(client):
    admin = _admin(client)
    stack_id = _make_kp("栈")
    queue_id = _make_kp("队列")
    question = _create_question(
        client,
        _headers(admin),
        knowledge_point_ids=[stack_id, queue_id],
    )
    assert question["difficulty"] == "easy"
    assert question["visibility"] == "shared"
    assert question["source"] == "admin"

    detail = client.get(
        f"/api/v1/admin/questions/{question['id']}", headers=_headers(admin)
    ).json()
    assert detail["answer"] == "B"
    roles = {item["knowledge_point_id"]: item["role"] for item in detail["knowledge_points"]}
    assert roles == {stack_id: "primary", queue_id: "secondary"}


def test_admin_attach_endpoint_rejects_container(client):
    admin = _admin(client)
    question = _create_question(client, _headers(admin))
    container_id = _make_kp("树与二叉树", node_type="container")
    response = client.post(
        f"/api/v1/admin/questions/{question['id']}/knowledge-points",
        headers=_headers(admin),
        json={"knowledge_point_id": container_id},
    )
    assert response.status_code == 400
    assert "目录节点" in response.json()["detail"]


def test_admin_create_with_container_id_rejected_atomically(client):
    """创建时携带 container：整体回滚，不留下半成品题目。"""
    admin = _admin(client)
    container_id = _make_kp("树与二叉树", node_type="container")
    payload = {
        "subject": "数据结构",
        "knowledge_point": "树",
        "stem": "s",
        "answer": "a",
        "knowledge_point_ids": [container_id],
    }
    response = client.post(
        "/api/v1/admin/questions", headers=_headers(admin), json=payload
    )
    assert response.status_code == 400
    with SessionLocal() as db:
        assert db.scalar(select(Question).where(Question.stem == "s")) is None


# ---------- 2. DB 级 container 禁令（复合外键） ----------


def test_db_level_composite_fk_rejects_container():
    """绕过 Service 直接 INSERT (kp_id, 'concept') 指向 container → IntegrityError。

    SQLite 默认不开外键，须自建引擎并 PRAGMA foreign_keys=ON
    （沿 test_knowledge_point_profile_m1 的 _fk_enforced_engine 模式）。
    """
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite://")
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):  # pragma: no cover - 每个新连接都要开
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    try:
        user = User(email="fk@test.com", username="fkuser", hashed_password="x")
        db.add(user)
        db.flush()
        container = KnowledgePoint(
            name="树与二叉树",
            normalized_name="树与二叉树",
            subject="数据结构",
            normalized_subject="数据结构",
            node_type="container",
        )
        db.add(container)
        db.flush()
        question = Question(
            user_id=user.id, subject="数据结构", knowledge_point="树",
            stem="s", answer="a", source="admin",
        )
        db.add(question)
        db.flush()
        # 直接 INSERT：kp_node_type 伪称 'concept' 但目标行是 container。
        association = QuestionKnowledgePoint(
            question_id=question.id,
            knowledge_point_id=container.id,
            kp_node_type="concept",
        )
        db.add(association)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
    finally:
        db.close()
        engine.dispose()


# ---------- 3. visibility：共享可见性 ----------


def test_shared_question_visible_and_answerable_by_other_user(client):
    admin = _admin(client)
    learner = _register(client, "m4learner@test.com", "m4learner")
    stack_id = _make_kp("栈")
    question = _create_question(client, _headers(admin), knowledge_point_ids=[stack_id])

    # 共享题库列表可见
    bank = client.get("/api/v1/question-bank", headers=_headers(learner)).json()
    assert [item["id"] for item in bank] == [question["id"]]
    # 知识点反查可见（普通用户 = 自己的题 ∪ shared）
    listing = client.get(
        f"/api/v1/knowledge-points/{stack_id}/questions", headers=_headers(learner)
    ).json()
    assert [item["id"] for item in listing] == [question["id"]]
    # 可以作答
    response = client.post(
        f"/api/v1/questions/{question['id']}/answers",
        headers=_headers(learner),
        json={"user_answer": "B"},
    )
    assert response.status_code == 201
    assert response.json()["is_correct"] is True


def test_other_user_private_question_still_404(client):
    """他人私题不可见不可做（owner 语义不变，仅扩大 shared）。"""
    _admin(client)
    owner = _register(client, "m4owner@test.com", "m4owner")
    stranger = _register(client, "m4stranger@test.com", "m4stranger")
    private_id = _make_private_question(owner["user"]["id"])

    # 不在共享题库
    bank = client.get("/api/v1/question-bank", headers=_headers(stranger)).json()
    assert bank == []
    # 不能作答
    assert (
        client.post(
            f"/api/v1/questions/{private_id}/answers",
            headers=_headers(stranger),
            json={"user_answer": "B"},
        ).status_code
        == 404
    )
    # owner 自己能作答
    assert (
        client.post(
            f"/api/v1/questions/{private_id}/answers",
            headers=_headers(owner),
            json={"user_answer": "B"},
        ).status_code
        == 201
    )


def test_question_bank_subject_and_difficulty_filters(client):
    admin = _admin(client)
    _create_question(client, _headers(admin), difficulty="easy", subject="数据结构")
    _create_question(
        client, _headers(admin), difficulty="hard", subject="操作系统",
        knowledge_point="进程", stem="进程切换发生在？", answer="A",
    )
    bank = client.get(
        "/api/v1/question-bank",
        headers=_headers(admin),
        params={"difficulty": "hard"},
    ).json()
    assert len(bank) == 1 and bank[0]["subject"] == "操作系统"
    bank = client.get(
        "/api/v1/question-bank", headers=_headers(admin), params={"subject": "数据结构"}
    ).json()
    assert len(bank) == 1 and bank[0]["difficulty"] == "easy"


# ---------- 4. 答题数据 + mastery ----------


def test_shared_question_answer_updates_mastery(client):
    admin = _admin(client)
    learner = _register(client, "m4mastery@test.com", "m4mastery")
    stack_id = _make_kp("栈")
    question = _create_question(client, _headers(admin), knowledge_point_ids=[stack_id])

    # 答对
    client.post(
        f"/api/v1/questions/{question['id']}/answers",
        headers=_headers(learner),
        json={"user_answer": "B"},
    )
    with SessionLocal() as db:
        record = db.scalar(
            select(AnswerRecord).where(AnswerRecord.question_id == question["id"])
        )
        assert record is not None and record.is_correct is True
        mastery = db.scalar(
            select(UserKnowledgePointMastery).where(
                UserKnowledgePointMastery.user_id == learner["user"]["id"],
                UserKnowledgePointMastery.knowledge_point_id == stack_id,
            )
        )
        assert mastery is not None
        assert mastery.attempt_count == 1
        assert mastery.correct_count == 1
        score_after_first = mastery.mastery_score

    # 再答一次（仍对）：分数单调不减、attempt 累计
    client.post(
        f"/api/v1/questions/{question['id']}/answers",
        headers=_headers(learner),
        json={"user_answer": "B"},
    )
    with SessionLocal() as db:
        mastery = db.scalar(
            select(UserKnowledgePointMastery).where(
                UserKnowledgePointMastery.user_id == learner["user"]["id"],
                UserKnowledgePointMastery.knowledge_point_id == stack_id,
            )
        )
        assert mastery.attempt_count == 2
        assert mastery.mastery_score >= score_after_first

    # 掌握度接口可读
    summary = client.get("/api/v1/mastery/summary", headers=_headers(learner)).json()
    assert summary["total"] == 1


def test_wrong_answer_creates_wrong_book_and_lowers_mastery(client):
    admin = _admin(client)
    learner = _register(client, "m4wrong@test.com", "m4wrong")
    stack_id = _make_kp("栈")
    question = _create_question(client, _headers(admin), knowledge_point_ids=[stack_id])

    client.post(
        f"/api/v1/questions/{question['id']}/answers",
        headers=_headers(learner),
        json={"user_answer": "A"},
    )
    with SessionLocal() as db:
        mastery = db.scalar(
            select(UserKnowledgePointMastery).where(
                UserKnowledgePointMastery.user_id == learner["user"]["id"]
            )
        )
        assert mastery.mastery_score < 50  # 初始 50，答错下降
    wrong_book = client.get("/api/v1/wrong-book", headers=_headers(learner)).json()
    assert [item["question_id"] for item in wrong_book] == [question["id"]]


# ---------- 5. 隔离：反查不被他人私题污染 ----------


def test_reverse_lookup_mixes_own_and_shared_only(client):
    admin = _admin(client)
    owner = _register(client, "m4mix@test.com", "m4mix")
    stack_id = _make_kp("栈")
    shared = _create_question(client, _headers(admin), knowledge_point_ids=[stack_id])
    # owner 的私题也绑定同一知识点（DB 直建 + 用户端绑定接口）
    private_id = _make_private_question(owner["user"]["id"])
    response = client.post(
        f"/api/v1/questions/{private_id}/knowledge-points",
        headers=_headers(owner),
        json={"knowledge_point_id": stack_id},
    )
    assert response.status_code == 201, response.text
    # 第三人只看到 shared
    stranger = _register(client, "m4mix2@test.com", "m4mix2")
    listing = client.get(
        f"/api/v1/knowledge-points/{stack_id}/questions", headers=_headers(stranger)
    ).json()
    assert {item["id"] for item in listing} == {shared["id"]}
    # owner 看到 shared + 自己的私题
    listing = client.get(
        f"/api/v1/knowledge-points/{stack_id}/questions", headers=_headers(owner)
    ).json()
    assert {item["id"] for item in listing} == {shared["id"], private_id}
    # container 反查返回空（不报错）
    container_id = _make_kp("树与二叉树", node_type="container")
    listing = client.get(
        f"/api/v1/knowledge-points/{container_id}/questions", headers=_headers(owner)
    ).json()
    assert listing == []


# ---------- 6. 覆盖统计 ----------


def test_knowledge_coverage_counts_concepts_only(client):
    admin = _admin(client)
    stack_id = _make_kp("栈")
    _make_kp("队列")
    _make_kp("树与二叉树", node_type="container")
    _create_question(client, _headers(admin), knowledge_point_ids=[stack_id])

    coverage = client.get(
        "/api/v1/admin/knowledge-coverage", headers=_headers(admin)
    ).json()
    # container 不计入 concept_total
    assert coverage["concept_total"] == 2
    assert coverage["covered"] == 1
    assert coverage["uncovered"] == 1
    item = next(i for i in coverage["items"] if i["subject"] == "数据结构")
    assert item["concept_total"] == 2
    assert item["covered"] == 1
    assert item["question_total"] == 1
