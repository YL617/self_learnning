"""大阶段 4 P0：知识节点类型（container | concept）的语义与门禁测试。

覆盖（对应设计方案 §2.6 的 T1~T10、T25~T29 与用户提示词的 T24 等）：

  词表与 DB 约束
    - 词表三方一致（model CHECK / schema Literal / service 常量）
    - 默认值：不传 node_type 的旧式 ORM 写入 → concept（T10 / T24 历史兼容）
    - DB CHECK 拒绝未知类型（T9）

  父子类型约束（T25~T29）
    - container→container / container→concept / concept→concept 允许
    - concept→container 拒绝（服务层显式业务异常，不靠 IntegrityError）
    - 改型导致非法结构时拒绝（父为 concept / 子含 container）

  下游门禁
    - 推荐：container 不进任何动作候选（T1）；data_scale 只统计 concept（T6）
    - 题目关联：primary / secondary 均拒绝 container（T2 / T3）
    - 掌握度：container 不计入 summary / weak（读取层防御）
    - 前置关系：两端任一为 container 均拒绝（T8）
    - AI 标注 / LLM 候选召回词表：不含 container（T4 / T7）

  HTTP 层
    - GET ?node_type= 真过滤；非法值 422
    - POST / PATCH 带 node_type；非法改型 → 400
    - 关联容器 → 400；前置端点容器 → 400；对容器 suggest → 400
"""

import uuid

import pytest
from sqlalchemy import delete, insert, select
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models import (
    AnswerRecord,
    KnowledgePoint,
    KnowledgePointPrerequisite,
    Question,
    QuestionKnowledgePoint,
    User,
    UserKnowledgePointMastery,
    WrongBookItem,
)
from app.services.knowledge_point_service import (
    KP_NODE_TYPES,
    KP_NODE_TYPE_CONCEPT,
    KP_NODE_TYPE_CONTAINER,
    InvalidNodeType,
    KnowledgePointService,
)

API = "/api/v1"
SUBJECT = "数据结构"


# ------------------------------------------------------------------ 环境


def _wipe() -> None:
    with SessionLocal() as db:
        db.execute(delete(KnowledgePointPrerequisite))
        db.execute(delete(AnswerRecord))
        db.execute(delete(WrongBookItem))
        db.execute(delete(UserKnowledgePointMastery))
        db.execute(delete(QuestionKnowledgePoint))
        db.execute(delete(Question))
        db.execute(delete(KnowledgePoint))
        db.commit()


@pytest.fixture(autouse=True)
def _clean_tables():
    _wipe()
    yield
    _wipe()


def _mk_kp(
    db,
    name: str,
    *,
    node_type: str | None = None,
    parent_id: int | None = None,
    status: str = "active",
    subject: str = SUBJECT,
) -> KnowledgePoint:
    kwargs: dict = {}
    if node_type is not None:
        kwargs["node_type"] = node_type
    item = KnowledgePoint(
        name=name,
        normalized_name=name.lower(),
        subject=subject,
        normalized_subject=subject.lower(),
        parent_id=parent_id,
        status=status,
        **kwargs,
    )
    db.add(item)
    db.flush()
    return item


def _mk_question(db, user_id: int) -> Question:
    question = Question(
        user_id=user_id,
        subject=SUBJECT,
        knowledge_point="占位",
        question_type="choice",
        stem="题干",
        answer="A",
    )
    db.add(question)
    db.flush()
    return question


def _mk_user(db) -> User:
    suffix = uuid.uuid4().hex[:10]
    user = User(
        email=f"p0_{suffix}@example.com",
        username=f"p0_{suffix}",
        hashed_password="x",
    )
    db.add(user)
    db.flush()
    return user


# ------------------------------------------------------------------ 词表 / DB 约束


def test_node_type_vocabulary_is_pinned_three_ways():
    """词表三方一致：service 常量 / schema Literal / DB CHECK。"""
    from sqlalchemy import CheckConstraint

    from app.schemas.knowledge import KnowledgePointNodeType, KnowledgePointRead

    assert set(KP_NODE_TYPES) == {"container", "concept"}
    assert set(KnowledgePointNodeType.__args__) == set(KP_NODE_TYPES)

    table = KnowledgePoint.__table__
    check = next(
        c
        for c in table.constraints
        if isinstance(c, CheckConstraint) and c.name == "ck_knowledge_points_node_type"
    )
    sql = str(check.sqltext)
    for value in KP_NODE_TYPES:
        assert f"'{value}'" in sql, value

    # Read 模型必须把 node_type 暴露给前端。
    assert "node_type" in KnowledgePointRead.model_fields


def test_node_type_column_is_not_null_with_concept_default():
    column = KnowledgePoint.__table__.c.node_type
    assert column.nullable is False
    assert str(column.server_default.arg) == "concept"
    assert any(i.name == "ix_knowledge_points_node_type" for i in KnowledgePoint.__table__.indexes)


def test_legacy_orm_insert_defaults_to_concept():
    """T10 / T24 历史兼容：不传 node_type 的旧式写入落为 concept。"""
    with SessionLocal() as db:
        item = _mk_kp(db, "旧式知识点")
        db.commit()
        assert item.node_type == KP_NODE_TYPE_CONCEPT
        assert db.get(KnowledgePoint, item.id).node_type == "concept"


def test_check_constraint_rejects_unknown_node_type():
    """T9：词表外的值由 DB CHECK 拒绝（不是靠应用层）。"""
    with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            db.execute(
                insert(KnowledgePoint).values(
                    name="非法类型",
                    normalized_name="非法类型",
                    subject=SUBJECT,
                    normalized_subject=SUBJECT.lower(),
                    status="active",
                    node_type="group",
                )
            )
        db.rollback()


# ------------------------------------------------------------------ 父子类型约束


def test_parent_child_type_matrix_allows_three_combinations():
    """T25/T26/T27：container→container、container→concept、concept→concept 允许。"""
    with SessionLocal() as db:
        service = KnowledgePointService(db)
        root = service.create(
            name="根目录", subject=SUBJECT, node_type=KP_NODE_TYPE_CONTAINER
        )
        sub_container = service.create(
            name="子目录",
            subject=SUBJECT,
            parent_id=root.id,
            node_type=KP_NODE_TYPE_CONTAINER,
        )
        leaf = service.create(
            name="知识点A",
            subject=SUBJECT,
            parent_id=sub_container.id,
            node_type=KP_NODE_TYPE_CONCEPT,
        )
        concept_parent = service.create(
            name="知识点父", subject=SUBJECT, node_type=KP_NODE_TYPE_CONCEPT
        )
        concept_child = service.create(
            name="知识点子",
            subject=SUBJECT,
            parent_id=concept_parent.id,
            node_type=KP_NODE_TYPE_CONCEPT,
        )
        db.commit()
        assert sub_container.parent_id == root.id
        assert leaf.parent_id == sub_container.id
        assert concept_child.parent_id == concept_parent.id


def test_parent_child_type_matrix_rejects_container_under_concept():
    """T28：concept→container 必须拒绝，且抛明确的业务异常。"""
    with SessionLocal() as db:
        service = KnowledgePointService(db)
        concept = service.create(
            name="父知识点", subject=SUBJECT, node_type=KP_NODE_TYPE_CONCEPT
        )
        with pytest.raises(InvalidNodeType):
            service.create(
                name="非法子目录",
                subject=SUBJECT,
                parent_id=concept.id,
                node_type=KP_NODE_TYPE_CONTAINER,
            )
        db.rollback()


def test_changing_type_to_container_rejected_when_parent_is_concept():
    """T29a：把已有 concept 改为 container，而其父仍是 concept → 拒绝。"""
    with SessionLocal() as db:
        service = KnowledgePointService(db)
        parent = service.create(
            name="父知识点", subject=SUBJECT, node_type=KP_NODE_TYPE_CONCEPT
        )
        child = service.create(
            name="子知识点",
            subject=SUBJECT,
            parent_id=parent.id,
            node_type=KP_NODE_TYPE_CONCEPT,
        )
        db.commit()

        from app.schemas.knowledge import KnowledgePointUpdate

        with pytest.raises(InvalidNodeType):
            service.update(
                child.id, KnowledgePointUpdate(node_type=KP_NODE_TYPE_CONTAINER)
            )
        db.rollback()


def test_changing_type_to_concept_rejected_when_children_are_containers():
    """T29b：把已有 container 改为 concept，而其下仍有 container 子节点 → 拒绝。"""
    with SessionLocal() as db:
        service = KnowledgePointService(db)
        container = service.create(
            name="目录节点", subject=SUBJECT, node_type=KP_NODE_TYPE_CONTAINER
        )
        service.create(
            name="子目录",
            subject=SUBJECT,
            parent_id=container.id,
            node_type=KP_NODE_TYPE_CONTAINER,
        )
        db.commit()

        from app.schemas.knowledge import KnowledgePointUpdate

        with pytest.raises(InvalidNodeType):
            service.update(
                container.id, KnowledgePointUpdate(node_type=KP_NODE_TYPE_CONCEPT)
            )
        db.rollback()


def test_create_rejects_unknown_node_type_value():
    with SessionLocal() as db:
        service = KnowledgePointService(db)
        with pytest.raises(ValueError):
            service.create(name="未知类型", subject=SUBJECT, node_type="group")
        db.rollback()


# ------------------------------------------------------------------ 推荐


def test_recommendation_candidates_exclude_containers():
    """T1：container 不出现在 4 类动作的候选装载里。"""
    from app.services.recommendation import RecommendationService

    with SessionLocal() as db:
        user = _mk_user(db)
        container = _mk_kp(db, "排序", node_type=KP_NODE_TYPE_CONTAINER)
        concept = _mk_kp(db, "快速排序", node_type=KP_NODE_TYPE_CONCEPT)
        db.commit()

        service = RecommendationService(db)
        loaded = service._knowledge_points()
        assert set(loaded) == {concept.id}
        assert all(row.node_type == KP_NODE_TYPE_CONCEPT for row in loaded.values())

        items = service.today(user.id)
        # 目录节点的 id 绝不能出现在任何推荐动作里。
        assert all(item.knowledge_point_id != container.id for item in items)
        # 出现即必须是 concept（且确实被装载过）。
        assert all(
            item.knowledge_point_id in loaded
            for item in items
            if item.knowledge_point_id is not None
        )


def test_data_scale_counts_concepts_only():
    """T6：规模快照的 knowledge_point_count 只统计 concept。"""
    from app.services.recommendation import data_scale

    with SessionLocal() as db:
        _mk_kp(db, "目录A", node_type=KP_NODE_TYPE_CONTAINER)
        _mk_kp(db, "目录B", node_type=KP_NODE_TYPE_CONTAINER)
        _mk_kp(db, "知识点1", node_type=KP_NODE_TYPE_CONCEPT)
        _mk_kp(db, "知识点2", node_type=KP_NODE_TYPE_CONCEPT)
        _mk_kp(db, "知识点3", node_type=KP_NODE_TYPE_CONCEPT)
        db.commit()
        snapshot = data_scale(db)
        assert snapshot.knowledge_point_count == 3


# ------------------------------------------------------------------ 题目关联


def test_attach_rejects_container_for_both_roles():
    """T2 / T3：primary 与 secondary 都不能关联 container。"""
    from app.services.question_knowledge_point_service import (
        NotLearnableNode,
        QuestionKnowledgePointService,
    )

    with SessionLocal() as db:
        user = _mk_user(db)
        question = _mk_question(db, user.id)
        container = _mk_kp(db, "排序", node_type=KP_NODE_TYPE_CONTAINER)
        db.commit()

        service = QuestionKnowledgePointService(db)
        for role in ("primary", "secondary"):
            with pytest.raises(NotLearnableNode):
                service.attach(question.id, container.id, role=role)
        db.rollback()
        assert db.scalar(select(QuestionKnowledgePoint.id)) is None


def test_concept_attach_still_works():
    from app.services.question_knowledge_point_service import (
        QuestionKnowledgePointService,
    )

    with SessionLocal() as db:
        user = _mk_user(db)
        question = _mk_question(db, user.id)
        concept = _mk_kp(db, "快速排序", node_type=KP_NODE_TYPE_CONCEPT)
        db.commit()

        row = QuestionKnowledgePointService(db).attach(question.id, concept.id)
        db.commit()
        assert row.knowledge_point_id == concept.id


def test_replace_rejects_container():
    from app.services.question_knowledge_point_service import (
        NotLearnableNode,
        QuestionKnowledgePointService,
    )

    with SessionLocal() as db:
        user = _mk_user(db)
        question = _mk_question(db, user.id)
        container = _mk_kp(db, "图", node_type=KP_NODE_TYPE_CONTAINER)
        db.commit()
        with pytest.raises(NotLearnableNode):
            QuestionKnowledgePointService(db).replace(
                question.id, [(container.id, "primary")]
            )
        db.rollback()


def test_list_questions_for_container_returns_empty():
    from app.services.question_knowledge_point_service import (
        QuestionKnowledgePointService,
    )

    with SessionLocal() as db:
        user = _mk_user(db)
        container = _mk_kp(db, "树与二叉树", node_type=KP_NODE_TYPE_CONTAINER)
        db.commit()
        assert QuestionKnowledgePointService(db).list_question_ids_for_knowledge_point(
            container.id, None
        ) == []


def test_validate_knowledge_point_for_subject_rejects_container():
    """出题入口同样拒绝 container。"""
    from app.services.question_knowledge_point_service import (
        NotLearnableNode,
        QuestionKnowledgePointService,
    )

    with SessionLocal() as db:
        container = _mk_kp(db, "串", node_type=KP_NODE_TYPE_CONTAINER)
        db.commit()
        with pytest.raises(NotLearnableNode):
            QuestionKnowledgePointService(db).validate_knowledge_point_for_subject(
                container.id, SUBJECT
            )


# ------------------------------------------------------------------ 掌握度


def test_container_mastery_row_is_not_counted():
    """container 即便有历史脏行，也不计入 summary / weak / 平均分。"""
    from app.services.mastery import MasteryService

    with SessionLocal() as db:
        user = _mk_user(db)
        container = _mk_kp(db, "查找", node_type=KP_NODE_TYPE_CONTAINER)
        weak_concept = _mk_kp(db, "散列表", node_type=KP_NODE_TYPE_CONCEPT)
        good_concept = _mk_kp(db, "顺序查找", node_type=KP_NODE_TYPE_CONCEPT)
        db.add_all(
            [
                UserKnowledgePointMastery(
                    user_id=user.id,
                    knowledge_point_id=container.id,
                    mastery_score=10,
                    attempt_count=5,
                    correct_count=0,
                    correct_streak=0,
                ),
                UserKnowledgePointMastery(
                    user_id=user.id,
                    knowledge_point_id=weak_concept.id,
                    mastery_score=30,
                    attempt_count=2,
                    correct_count=0,
                    correct_streak=0,
                ),
                UserKnowledgePointMastery(
                    user_id=user.id,
                    knowledge_point_id=good_concept.id,
                    mastery_score=90,
                    attempt_count=2,
                    correct_count=2,
                    correct_streak=2,
                ),
            ]
        )
        db.commit()

        service = MasteryService(db)
        assert service.count_for_user(user.id) == 2
        assert service.count_weak(user.id) == 1
        assert service.average_score(user.id) == 60.0  # (30 + 90) / 2，不含容器
        assert {row.knowledge_point_id for row in service.list_for_user(user.id)} == {
            weak_concept.id,
            good_concept.id,
        }
        assert {row.knowledge_point_id for row in service.list_weak(user.id)} == {
            weak_concept.id
        }


# ------------------------------------------------------------------ 前置关系


def test_prerequisite_rejects_container_endpoints():
    """T8：两端任一为 container 均拒绝（三种组合）。"""
    from app.services.prerequisite import NotLearnableNode, PrerequisiteService

    with SessionLocal() as db:
        container = _mk_kp(db, "排序", node_type=KP_NODE_TYPE_CONTAINER)
        concept = _mk_kp(db, "快速排序", node_type=KP_NODE_TYPE_CONCEPT)
        concept2 = _mk_kp(db, "堆排序", node_type=KP_NODE_TYPE_CONCEPT)
        db.commit()

        service = PrerequisiteService(db)
        with pytest.raises(NotLearnableNode):
            service.add(knowledge_point_id=container.id, prerequisite_id=concept.id)
        with pytest.raises(NotLearnableNode):
            service.add(knowledge_point_id=concept.id, prerequisite_id=container.id)
        with pytest.raises(NotLearnableNode):
            service.add(knowledge_point_id=container.id, prerequisite_id=container.id)
        # 合法组合仍可用
        edge = service.add(knowledge_point_id=concept2.id, prerequisite_id=concept.id)
        db.commit()
        assert edge.prerequisite_id == concept.id


def test_llm_candidate_pool_excludes_containers():
    """T4 / T7：AI 标注 / 前置提议的候选召回词表只含 concept。"""
    from app.services.prerequisite import PrerequisiteService
    from app.services.prerequisite_suggest import _candidates

    with SessionLocal() as db:
        container = _mk_kp(db, "排序", node_type=KP_NODE_TYPE_CONTAINER)
        target = _mk_kp(db, "快速排序", node_type=KP_NODE_TYPE_CONCEPT)
        other = _mk_kp(db, "堆排序", node_type=KP_NODE_TYPE_CONCEPT)
        db.commit()

        candidates = _candidates(PrerequisiteService(db), target)
        ids = {row.id for row in candidates}
        assert container.id not in ids
        assert other.id in ids
        # 目标自己也不在候选里
        assert target.id not in ids


def test_suggest_rejects_container_target():
    from app.services.prerequisite import NotLearnableNode
    from app.services.prerequisite_suggest import suggest_prerequisites

    with SessionLocal() as db:
        container = _mk_kp(db, "图", node_type=KP_NODE_TYPE_CONTAINER)
        db.commit()
        with pytest.raises(NotLearnableNode):
            suggest_prerequisites(db, container.id)


# ------------------------------------------------------------------ HTTP 层


def _register(client, role: str = "admin") -> dict:
    suffix = uuid.uuid4().hex[:10]
    response = client.post(
        f"{API}/auth/register",
        json={
            "email": f"nt_{suffix}@example.com",
            "username": f"nt_{suffix}",
            "password": "123456",
        },
    )
    assert response.status_code == 201, response.text
    auth = response.json()
    if role != "user":
        with SessionLocal() as db:
            db.get(User, auth["user"]["id"]).role = role
            db.commit()
    return auth


def _headers(auth: dict) -> dict:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def test_api_list_filters_by_node_type(client):
    headers = _headers(_register(client))
    with SessionLocal() as db:
        _mk_kp(db, "排序", node_type=KP_NODE_TYPE_CONTAINER)
        concept = _mk_kp(db, "快速排序", node_type=KP_NODE_TYPE_CONCEPT)
        db.commit()
        concept_id = concept.id

    all_rows = client.get(f"{API}/knowledge-points", headers=headers)
    assert all_rows.status_code == 200
    assert {row["name"] for row in all_rows.json()} == {"排序", "快速排序"}

    concepts = client.get(
        f"{API}/knowledge-points", headers=headers, params={"node_type": "concept"}
    )
    assert concepts.status_code == 200
    assert [row["id"] for row in concepts.json()] == [concept_id]
    assert all(row["node_type"] == "concept" for row in concepts.json())

    containers = client.get(
        f"{API}/knowledge-points", headers=headers, params={"node_type": "container"}
    )
    assert containers.status_code == 200
    assert {row["name"] for row in containers.json()} == {"排序"}


def test_api_list_rejects_invalid_node_type(client):
    headers = _headers(_register(client))
    response = client.get(
        f"{API}/knowledge-points", headers=headers, params={"node_type": "group"}
    )
    assert response.status_code == 422, response.text


def test_api_create_defaults_to_concept_and_accepts_container(client):
    headers = _headers(_register(client))
    default = client.post(
        f"{API}/knowledge-points", headers=headers, json={"name": "默认概念", "subject": SUBJECT}
    )
    assert default.status_code == 201, default.text
    assert default.json()["node_type"] == "concept"

    container = client.post(
        f"{API}/knowledge-points",
        headers=headers,
        json={"name": "目录", "subject": SUBJECT, "node_type": "container"},
    )
    assert container.status_code == 201, container.text
    assert container.json()["node_type"] == "container"


def test_api_update_rejects_illegal_type_transition(client):
    headers = _headers(_register(client))
    parent = client.post(
        f"{API}/knowledge-points",
        headers=headers,
        json={"name": "父概念", "subject": SUBJECT, "node_type": "concept"},
    ).json()
    child = client.post(
        f"{API}/knowledge-points",
        headers=headers,
        json={
            "name": "子概念",
            "subject": SUBJECT,
            "parent_id": parent["id"],
            "node_type": "concept",
        },
    ).json()

    response = client.patch(
        f"{API}/knowledge-points/{child['id']}", headers=headers, json={"node_type": "container"}
    )
    assert response.status_code == 400, response.text
    assert "目录" in response.json()["detail"]


def test_api_attach_rejects_container(client):
    headers = _headers(_register(client))
    container = client.post(
        f"{API}/knowledge-points",
        headers=headers,
        json={"name": "图", "subject": SUBJECT, "node_type": "container"},
    ).json()
    with SessionLocal() as db:
        user = db.scalar(select(User).limit(1))
        question = _mk_question(db, user.id)
        db.commit()
        question_id = question.id

    response = client.post(
        f"{API}/questions/{question_id}/knowledge-points",
        headers=headers,
        json={"knowledge_point_id": container["id"], "role": "primary"},
    )
    assert response.status_code == 400, response.text
    assert "目录" in response.json()["detail"]


def test_api_prerequisite_rejects_container(client):
    headers = _headers(_register(client))
    container = client.post(
        f"{API}/knowledge-points",
        headers=headers,
        json={"name": "排序", "subject": SUBJECT, "node_type": "container"},
    ).json()
    concept = client.post(
        f"{API}/knowledge-points",
        headers=headers,
        json={"name": "快速排序", "subject": SUBJECT, "node_type": "concept"},
    ).json()

    response = client.post(
        f"{API}/knowledge-points/{concept['id']}/prerequisites",
        headers=headers,
        json={"prerequisite_id": container["id"], "strength": 100},
    )
    assert response.status_code == 400, response.text
    assert "目录" in response.json()["detail"]


def test_api_suggest_rejects_container_target(client):
    headers = _headers(_register(client))
    container = client.post(
        f"{API}/knowledge-points",
        headers=headers,
        json={"name": "图", "subject": SUBJECT, "node_type": "container"},
    ).json()
    response = client.post(
        f"{API}/knowledge-points/{container['id']}/prerequisites/suggest", headers=headers
    )
    assert response.status_code == 400, response.text
