"""大阶段 2：学习状态闭环端到端验证。

链路：答题 → EvaluationResult → 知识点掌握度 → 错题本 → 复习排期 → 再次复习。

不新增 migration 断言、不污染生产数据；全部使用测试库与 mock AI。
"""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import delete, func, select

from app.core.database import SessionLocal
from app.models import (
    AnswerRecord,
    KnowledgePoint,
    Question,
    QuestionKnowledgePoint,
    User,
    UserKnowledgePointMastery,
    WrongBookItem,
)

API = "/api/v1"

# conftest 的 mock AI gateway 固定返回 subject="Mock Subject"、答案 "A"。
AI_SUBJECT = "Mock Subject"
CORRECT_ANSWER = "A"
WRONG_ANSWER = "B"


def _wipe() -> None:
    with SessionLocal() as db:
        db.execute(delete(AnswerRecord))
        db.execute(delete(WrongBookItem))
        db.execute(delete(UserKnowledgePointMastery))
        db.execute(delete(QuestionKnowledgePoint))
        db.execute(delete(Question))
        db.execute(delete(KnowledgePoint))
        db.commit()


@pytest.fixture(autouse=True)
def _clean_learning_tables():
    _wipe()
    yield
    _wipe()


def _register(client, role: str = "user") -> dict:
    suffix = uuid.uuid4().hex[:10]
    response = client.post(
        f"{API}/auth/register",
        json={
            "email": f"loop_{suffix}@example.com",
            "username": f"loop_{suffix}",
            "password": "123456",
        },
    )
    assert response.status_code == 201, response.text
    auth = response.json()
    if role != "user":
        with SessionLocal() as db:
            user = db.get(User, auth["user"]["id"])
            user.role = role
            db.commit()
    return auth


def _headers(auth: dict) -> dict:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _create_kp(client, headers, name: str, subject: str = AI_SUBJECT) -> dict:
    response = client.post(
        f"{API}/knowledge-points", headers=headers, json={"name": name, "subject": subject}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _generate(client, headers, *, knowledge_point_id=None, count: int = 1) -> list[dict]:
    payload = {
        "subject": AI_SUBJECT,
        "knowledge_point": "栈",
        "count": count,
        "question_type": "choice",
    }
    if knowledge_point_id is not None:
        payload["knowledge_point_id"] = knowledge_point_id
    response = client.post(f"{API}/questions/generate", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _answer(client, headers, question_id: int, value: str, spent: int = 0) -> dict:
    response = client.post(
        f"{API}/questions/{question_id}/answers",
        headers=headers,
        json={"user_answer": value, "spent_seconds": spent},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _mastery(client, headers) -> list[dict]:
    response = client.get(f"{API}/mastery", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _mastery_of(client, headers, kp_id: int) -> dict | None:
    response = client.get(f"{API}/mastery/{kp_id}", headers=headers)
    if response.status_code == 404:
        return None
    assert response.status_code == 200, response.text
    return response.json()


def _wrong_book(client, headers) -> list[dict]:
    response = client.get(f"{API}/wrong-book", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _prepared_question(client, *, kp_name: str = "栈"):
    """建点 → 出题（带结构化知识点）→ 返回 (知识点, 学生 headers, 题目, 学生)。"""
    admin = _register(client, "admin")
    student = _register(client, "user")
    admin_headers, student_headers = _headers(admin), _headers(student)
    kp = _create_kp(client, admin_headers, kp_name)
    question = _generate(client, student_headers, knowledge_point_id=kp["id"])[0]
    return kp, student_headers, question, student


# ------------------------------------------------------------------ 掌握度


def test_first_correct_answer_creates_mastery_and_raises_score(client):
    kp, headers, question, _ = _prepared_question(client)

    assert _mastery(client, headers) == []
    _answer(client, headers, question["id"], CORRECT_ANSWER, spent=12)

    rows = _mastery(client, headers)
    assert len(rows) == 1
    row = rows[0]
    assert row["knowledge_point_id"] == kp["id"]
    assert row["mastery_score"] > 50
    assert row["attempt_count"] == 1
    assert row["correct_count"] == 1
    assert row["correct_streak"] == 1
    assert row["last_answered_at"] is not None
    assert row["last_correct_at"] is not None
    assert row["knowledge_point"]["name"] == "栈"
    assert row["knowledge_point"]["subject"] == AI_SUBJECT


def test_wrong_answer_lowers_mastery_and_enters_wrong_book(client):
    kp, headers, question, _ = _prepared_question(client)

    _answer(client, headers, question["id"], WRONG_ANSWER)

    row = _mastery_of(client, headers, kp["id"])
    assert row is not None
    assert row["mastery_score"] < 50
    assert row["correct_count"] == 0
    assert row["last_correct_at"] is None

    items = _wrong_book(client, headers)
    assert len(items) == 1
    assert items[0]["question_id"] == question["id"]
    assert items[0]["review_stage"] == 1
    assert items[0]["next_review_date"] == (date.today() + timedelta(days=1)).isoformat()
    assert items[0]["mastered"] is False


def test_score_stays_within_0_100_over_many_answers(client):
    _, headers, question, _ = _prepared_question(client)
    for _ in range(8):
        _answer(client, headers, question["id"], CORRECT_ANSWER)
        row = _mastery(client, headers)[0]
        assert 0 <= row["mastery_score"] <= 100
    for _ in range(30):
        _answer(client, headers, question["id"], WRONG_ANSWER)
        row = _mastery(client, headers)[0]
        assert 0 <= row["mastery_score"] <= 100


def test_repeated_correct_answers_accumulate_and_are_monotonic(client):
    _, headers, question, _ = _prepared_question(client)

    scores = []
    for _ in range(3):
        _answer(client, headers, question["id"], CORRECT_ANSWER)
        scores.append(_mastery(client, headers)[0]["mastery_score"])

    assert scores == sorted(scores)
    assert scores[0] < scores[-1]
    row = _mastery(client, headers)[0]
    assert row["attempt_count"] == 3
    assert row["correct_count"] == 3
    assert row["correct_streak"] == 3


def test_multi_knowledge_point_updates_both_with_primary_heavier(client):
    admin = _register(client, "admin")
    student = _register(client, "user")
    admin_headers, headers = _headers(admin), _headers(student)

    primary = _create_kp(client, admin_headers, "栈")
    secondary = _create_kp(client, admin_headers, "递归")
    question = _generate(client, headers, knowledge_point_id=primary["id"])[0]

    attached = client.post(
        f"{API}/questions/{question['id']}/knowledge-points",
        headers=headers,
        json={"knowledge_point_id": secondary["id"], "role": "secondary"},
    )
    assert attached.status_code == 201, attached.text

    _answer(client, headers, question["id"], CORRECT_ANSWER)

    rows = {row["knowledge_point_id"]: row for row in _mastery(client, headers)}
    assert set(rows) == {primary["id"], secondary["id"]}
    # 同一道题同时影响两个知识点，但主知识点权重更大。
    assert rows[primary["id"]]["mastery_score"] > rows[secondary["id"]]["mastery_score"]


def test_legacy_question_without_structured_kp_keeps_old_behaviour(client):
    student = _register(client, "user")
    headers = _headers(student)
    question = _generate(client, headers)[0]

    _answer(client, headers, question["id"], WRONG_ANSWER)

    items = _wrong_book(client, headers)
    assert len(items) == 1
    assert items[0]["question"]["question_type"] == "choice"
    # legacy 题目没有结构化知识点 → 不产生掌握度，旧行为完全不变。
    assert _mastery(client, headers) == []


# ------------------------------------------------------------------ 错题 / 复习


def test_wrong_book_item_is_unique_per_question(client):
    _, headers, question, _ = _prepared_question(client)

    _answer(client, headers, question["id"], WRONG_ANSWER)
    _answer(client, headers, question["id"], WRONG_ANSWER)

    items = _wrong_book(client, headers)
    # 一个用户 + 一道题只保留一条错题记录。
    assert len(items) == 1
    # review_count 统计"进入错题本之后的复习次数"，首次答错不计入。
    assert items[0]["review_count"] == 1
    # 再次答错：阶段保持在第 1 阶段（不回退到 0）。
    assert items[0]["review_stage"] == 1


def test_correct_review_advances_stage_and_delays_next_review(client):
    _, headers, question, _ = _prepared_question(client)

    _answer(client, headers, question["id"], WRONG_ANSWER)
    assert _wrong_book(client, headers)[0]["review_stage"] == 1

    _answer(client, headers, question["id"], CORRECT_ANSWER)
    item = _wrong_book(client, headers)[0]
    assert item["review_stage"] == 2
    assert item["next_review_date"] == (date.today() + timedelta(days=3)).isoformat()
    assert item["review_count"] == 1
    # 复习后答对：掌握度按复习系数增长，并记录 last_reviewed_at。
    row = _mastery(client, headers)[0]
    assert row["last_reviewed_at"] is not None


def test_wrong_review_regresses_stage(client):
    _, headers, question, _ = _prepared_question(client)

    _answer(client, headers, question["id"], WRONG_ANSWER)
    _answer(client, headers, question["id"], CORRECT_ANSWER)  # → stage 2
    _answer(client, headers, question["id"], CORRECT_ANSWER)  # → stage 3
    assert _wrong_book(client, headers)[0]["review_stage"] == 3

    _answer(client, headers, question["id"], WRONG_ANSWER)
    item = _wrong_book(client, headers)[0]
    assert item["review_stage"] == 2
    assert item["next_review_date"] == (date.today() + timedelta(days=3)).isoformat()


def test_repeated_stable_correct_marks_mastered(client):
    _, headers, question, _ = _prepared_question(client)

    _answer(client, headers, question["id"], WRONG_ANSWER)
    for _ in range(5):
        _answer(client, headers, question["id"], CORRECT_ANSWER)

    item = _wrong_book(client, headers)[0]
    assert item["mastered"] is True
    assert item["review_stage"] == 5
    # 已掌握 → 不再出现在到期复习队列。
    due = client.get(f"{API}/wrong-book/review", headers=headers)
    assert due.status_code == 200
    assert due.json() == []


def test_due_review_queue_after_date_passes(client):
    _, headers, question, _ = _prepared_question(client)
    _answer(client, headers, question["id"], WRONG_ANSWER)
    item = _wrong_book(client, headers)[0]

    assert client.get(f"{API}/wrong-book/review", headers=headers).json() == []

    with SessionLocal() as db:
        row = db.get(WrongBookItem, item["id"])
        row.next_review_date = date.today() - timedelta(days=1)
        db.commit()

    due = client.get(f"{API}/wrong-book/review", headers=headers).json()
    assert [entry["id"] for entry in due] == [item["id"]]


def test_wrong_book_patch_review_and_mastery_toggle(client):
    _, headers, question, _ = _prepared_question(client)
    _answer(client, headers, question["id"], WRONG_ANSWER)
    item = _wrong_book(client, headers)[0]

    reviewed = client.patch(
        f"{API}/wrong-book/{item['id']}", headers=headers, json={"reviewed": True}
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["review_stage"] == 2
    assert reviewed.json()["next_review_date"] == (
        date.today() + timedelta(days=3)
    ).isoformat()

    mastered = client.patch(
        f"{API}/wrong-book/{item['id']}", headers=headers, json={"mastered": True}
    )
    assert mastered.status_code == 200
    assert mastered.json()["mastered"] is True

    relearn = client.patch(
        f"{API}/wrong-book/{item['id']}", headers=headers, json={"mastered": False}
    )
    assert relearn.status_code == 200
    assert relearn.json()["mastered"] is False
    assert relearn.json()["review_stage"] == 1
    assert relearn.json()["next_review_date"] == (
        date.today() + timedelta(days=1)
    ).isoformat()


def test_reviewing_a_mastered_item_is_rejected(client):
    _, headers, question, _ = _prepared_question(client)
    _answer(client, headers, question["id"], WRONG_ANSWER)
    item = _wrong_book(client, headers)[0]
    client.patch(f"{API}/wrong-book/{item['id']}", headers=headers, json={"mastered": True})

    response = client.patch(
        f"{API}/wrong-book/{item['id']}", headers=headers, json={"reviewed": True}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "该错题已标记为掌握，无需重复复习"


def test_internal_source_never_exposed_in_wrong_book_payload(client):
    _, headers, question, _ = _prepared_question(client)
    _answer(client, headers, question["id"], WRONG_ANSWER)
    item = _wrong_book(client, headers)[0]
    assert set(item) == {
        "id",
        "question_id",
        "review_count",
        "mastered",
        "review_stage",
        "next_review_date",
        "last_reviewed_at",
        "created_at",
        "question",
    }


# ------------------------------------------------------------------ 事务 / 权限 / API


def test_mastery_failure_rolls_back_the_whole_answer(client, monkeypatch):
    _, headers, question, _ = _prepared_question(client)

    from app.services.mastery import MasteryService

    def boom(self, user_id, result, **kwargs):
        raise RuntimeError("mastery exploded")

    monkeypatch.setattr(MasteryService, "apply_evaluation", boom)

    response = client.post(
        f"{API}/questions/{question['id']}/answers",
        headers=headers,
        json={"user_answer": CORRECT_ANSWER},
    )
    assert response.status_code == 500
    assert "未保存" in response.json()["detail"]

    # 不允许出现"答案已保存但掌握度没更新"的半完成状态。
    with SessionLocal() as db:
        assert db.scalar(select(func.count(AnswerRecord.id))) == 0
        assert db.scalar(select(func.count(WrongBookItem.id))) == 0
        assert db.scalar(select(func.count(UserKnowledgePointMastery.id))) == 0


def test_mastery_endpoints_require_authentication(client):
    assert client.get(f"{API}/mastery").status_code == 401
    assert client.get(f"{API}/mastery/weak").status_code == 401
    assert client.get(f"{API}/mastery/summary").status_code == 401
    assert client.get(f"{API}/mastery/1").status_code == 401


def test_mastery_is_scoped_to_the_current_user(client):
    kp, headers_a, question, _ = _prepared_question(client)
    _answer(client, headers_a, question["id"], CORRECT_ANSWER)

    other = _register(client, "user")
    other_headers = _headers(other)
    assert _mastery(client, other_headers) == []
    assert _mastery_of(client, other_headers, kp["id"]) is None


def test_answering_another_users_question_is_rejected(client):
    _, _, question, _ = _prepared_question(client)
    other = _register(client, "user")
    other_headers = _headers(other)

    response = client.post(
        f"{API}/questions/{question['id']}/answers",
        headers=other_headers,
        json={"user_answer": CORRECT_ANSWER},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "题目不存在"


def test_mastery_detail_404_for_known_kp_without_history(client):
    admin = _register(client, "admin")
    student = _register(client, "user")
    kp = _create_kp(client, _headers(admin), "队列")

    response = client.get(f"{API}/mastery/{kp['id']}", headers=_headers(student))
    assert response.status_code == 404
    assert response.json()["detail"] == "暂无该知识点的掌握度记录"

    assert client.get(f"{API}/mastery/999999", headers=_headers(student)).status_code == 404


def test_weak_list_and_summary(client):
    admin = _register(client, "admin")
    student = _register(client, "user")
    admin_headers, headers = _headers(admin), _headers(student)

    strong = _create_kp(client, admin_headers, "栈")
    weak = _create_kp(client, admin_headers, "递归")
    question_a = _generate(client, headers, knowledge_point_id=strong["id"])[0]
    question_b = _generate(client, headers, knowledge_point_id=weak["id"])[0]

    _answer(client, headers, question_a["id"], CORRECT_ANSWER)
    _answer(client, headers, question_a["id"], CORRECT_ANSWER)
    _answer(client, headers, question_b["id"], WRONG_ANSWER)

    weak_rows = client.get(f"{API}/mastery/weak", headers=headers).json()
    assert [row["knowledge_point_id"] for row in weak_rows] == [weak["id"]]
    assert weak_rows[0]["mastery_score"] < 60

    all_rows = {row["knowledge_point_id"]: row for row in _mastery(client, headers)}
    assert all_rows[strong["id"]]["mastery_score"] > 60

    summary = client.get(f"{API}/mastery/summary", headers=headers).json()
    assert summary["total"] == 2
    assert summary["weak_count"] == 1
    # 首次答错的复习排期是"明天"，因此今天没有到期项。
    assert summary["today_review_count"] == 0
    assert 0 < summary["average_score"] < 100
    assert summary["weak_threshold"] == 60

    # 到期后（把排期改到昨天）今日待复习数量即为 1。
    due_item = _wrong_book(client, headers)[0]
    with SessionLocal() as db:
        row = db.get(WrongBookItem, due_item["id"])
        row.next_review_date = date.today() - timedelta(days=1)
        db.commit()
    assert client.get(f"{API}/mastery/summary", headers=headers).json()[
        "today_review_count"
    ] == 1


def test_mastery_list_only_contains_attempted_knowledge_points(client):
    admin = _register(client, "admin")
    student = _register(client, "user")
    admin_headers, headers = _headers(admin), _headers(student)

    attempted = _create_kp(client, admin_headers, "栈")
    _create_kp(client, admin_headers, "从未作答")
    question = _generate(client, headers, knowledge_point_id=attempted["id"])[0]
    _answer(client, headers, question["id"], CORRECT_ANSWER)

    rows = _mastery(client, headers)
    assert [row["knowledge_point_id"] for row in rows] == [attempted["id"]]


def test_knowledge_point_with_mastery_cannot_be_deleted(client):
    kp, headers, question, student = _prepared_question(client)
    _answer(client, headers, question["id"], CORRECT_ANSWER)

    # 先解除题目关联，剩下的唯一阻止因素就是用户掌握度记录。
    detached = client.delete(
        f"{API}/questions/{question['id']}/knowledge-points/{kp['id']}", headers=headers
    )
    assert detached.status_code == 204, detached.text

    # 同一用户提升为管理员后尝试删除：掌握度存在时必须拒绝，避免静默清空学习进度。
    with SessionLocal() as db:
        user = db.get(User, student["user"]["id"])
        user.role = "admin"
        db.commit()

    response = client.delete(f"{API}/knowledge-points/{kp['id']}", headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "知识点已有用户掌握度记录，无法删除"
