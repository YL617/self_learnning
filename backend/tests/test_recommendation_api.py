"""大阶段 3：今日建议 API（/recommendations/today）与前置关系接口的端到端验证。

重点：空态、未认证、跨用户隔离、legacy 无知识点题目、建议只读（不写 PlanItem）、
以及「前置未满足 → 满足」对 learn_new 候选的影响。
"""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import delete, func, select

from app.core.database import SessionLocal
from app.models import (
    AnswerRecord,
    KnowledgePoint,
    KnowledgePointPrerequisite,
    PlanItem,
    Question,
    QuestionKnowledgePoint,
    StudyPlan,
    User,
    UserKnowledgePointMastery,
    UserProfile,
    WrongBookItem,
)

API = "/api/v1"
# conftest 的 mock AI 固定返回 subject="Mock Subject"、答案 "A"。
AI_SUBJECT = "Mock Subject"
CORRECT_ANSWER = "A"
WRONG_ANSWER = "B"


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


def _register(client, role: str = "user") -> dict:
    suffix = uuid.uuid4().hex[:10]
    response = client.post(
        f"{API}/auth/register",
        json={
            "email": f"rec_{suffix}@example.com",
            "username": f"rec_{suffix}",
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


def _add_edge(client, headers, dependent_id: int, prerequisite_id: int, strength: int = 100):
    response = client.post(
        f"{API}/knowledge-points/{dependent_id}/prerequisites",
        headers=headers,
        json={"prerequisite_id": prerequisite_id, "strength": strength},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _generate(client, headers, *, knowledge_point_id: int | None = None, subject: str = AI_SUBJECT) -> dict:
    payload = {
        "subject": subject,
        "knowledge_point": "栈",
        "count": 1,
        "question_type": "choice",
    }
    if knowledge_point_id is not None:
        payload["knowledge_point_id"] = knowledge_point_id
    response = client.post(f"{API}/questions/generate", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()[0]


def _answer(client, headers, question_id: int, value: str) -> dict:
    response = client.post(
        f"{API}/questions/{question_id}/answers",
        headers=headers,
        json={"user_answer": value, "spent_seconds": 5},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _today(client, headers, limit: int | None = None) -> dict:
    params = {} if limit is None else {"limit": limit}
    response = client.get(f"{API}/recommendations/today", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _make_due(question_id: int, days_ago: int = 2) -> None:
    with SessionLocal() as db:
        item = db.scalar(
            select(WrongBookItem).where(WrongBookItem.question_id == question_id)
        )
        assert item is not None
        item.next_review_date = date.today() - timedelta(days=days_ago)
        db.commit()


def _raise_mastery(user_id: int, knowledge_point_id: int, score: int) -> None:
    with SessionLocal() as db:
        row = db.scalar(
            select(UserKnowledgePointMastery).where(
                UserKnowledgePointMastery.user_id == user_id,
                UserKnowledgePointMastery.knowledge_point_id == knowledge_point_id,
            )
        )
        assert row is not None
        row.mastery_score = score
        db.commit()


def _set_goals(user_id: int, goals: str) -> None:
    with SessionLocal() as db:
        profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
        if profile is None:
            profile = UserProfile(user_id=user_id)
            db.add(profile)
        profile.goals = goals
        db.commit()


def _prepare(client, *, dependent: str = "树", prerequisite: str = "链表"):
    """管理员建两点并连前置；学生出题（挂在 pr prerequisite 上）。"""
    admin = _register(client, "admin")
    student = _register(client, "user")
    admin_headers, student_headers = _headers(admin), _headers(student)
    base = _create_kp(client, admin_headers, prerequisite)
    advanced = _create_kp(client, admin_headers, dependent)
    _add_edge(client, admin_headers, advanced["id"], base["id"])
    question = _generate(client, student_headers, knowledge_point_id=base["id"])
    return {
        "admin": admin_headers,
        "student": student_headers,
        "student_user": student["user"],
        "base": base,
        "advanced": advanced,
        "question": question,
    }


# ---------------------------------------------------------------- 鉴权与空态
def test_recommendations_require_authentication(client):
    assert client.get(f"{API}/recommendations/today").status_code == 401


def test_empty_state_returns_no_items_but_ready_shape(client):
    student = _register(client, "user")
    payload = _today(client, _headers(student))
    assert payload["items"] == []
    assert payload["date"] == date.today().isoformat()
    assert payload["weak_threshold"] == 60
    assert payload["ready_threshold"] == 70


# ---------------------------------------------------------------- learn_new
def test_learn_new_surfaces_only_unblocked_root_knowledge_point(client):
    ctx = _prepare(client)
    payload = _today(client, ctx["student"])

    names = [item["knowledge_point_name"] for item in payload["items"]]
    assert "链表" in names
    assert "树" not in names  # 硬前置「链表」未满足 → 不应推荐

    item = payload["items"][0]
    assert item["action"] == "learn_new"
    assert item["order"] == 1
    assert "没有前置知识点" in item["reason"]
    assert item["components"]["base"] > 0


def test_blocked_knowledge_point_unlocks_after_prerequisite_mastered(client):
    ctx = _prepare(client)
    _answer(client, ctx["student"], ctx["question"]["id"], CORRECT_ANSWER)
    _raise_mastery(ctx["student_user"]["id"], ctx["base"]["id"], 82)

    payload = _today(client, ctx["student"])
    names = [item["knowledge_point_name"] for item in payload["items"]]
    assert "树" in names
    advanced = next(item for item in payload["items"] if item["knowledge_point_name"] == "树")
    assert advanced["action"] == "learn_new"
    assert "已满足开始条件" in advanced["reason"]
    assert "链表" in advanced["reason"]  # 理由必须引用真实前置名


# ---------------------------------------------------------------- 薄弱与错题
def test_wrong_answer_yields_review_weak_with_reason(client):
    ctx = _prepare(client)
    _answer(client, ctx["student"], ctx["question"]["id"], WRONG_ANSWER)

    payload = _today(client, ctx["student"])
    item = next(
        item for item in payload["items"] if item["knowledge_point_id"] == ctx["base"]["id"]
    )
    assert item["action"] == "review_weak"
    assert "低于薄弱线" in item["reason"]
    assert item["question_ids"] == [ctx["question"]["id"]]


def test_due_wrong_book_item_outranks_weak_review(client):
    ctx = _prepare(client)
    _answer(client, ctx["student"], ctx["question"]["id"], WRONG_ANSWER)
    before = _today(client, ctx["student"])
    assert before["items"][0]["action"] == "review_weak"

    _make_due(ctx["question"]["id"], days_ago=2)
    after = _today(client, ctx["student"])
    top = after["items"][0]
    assert top["action"] == "review_wrong"
    assert top["order"] == 1
    assert top["knowledge_point_id"] == ctx["base"]["id"]
    assert "已到复习日" in top["reason"]
    assert "逾期 2 天" in top["reason"]
    assert top["question_ids"] == [ctx["question"]["id"]]

    # 同一知识点只保留得分最高的动作，不会既 review_wrong 又 review_weak
    assert [item["knowledge_point_id"] for item in after["items"]].count(
        ctx["base"]["id"]
    ) == 1


def test_recent_activity_does_not_raise_scores(client):
    """刚答过→降权；引擎不因为"刚做过"就把同一项顶到最前（避免刷同一个点）。"""
    ctx = _prepare(client)
    _answer(client, ctx["student"], ctx["question"]["id"], WRONG_ANSWER)
    payload = _today(client, ctx["student"])
    item = payload["items"][0]
    assert item["components"]["recency"] < 1.0


# ---------------------------------------------------------------- 只读与隔离
def _plan_item_count(user_id: int) -> int:
    """只统计该用户自己的计划项。

    plan_items 不参与 _wipe()（它是其它测试文件的产物），
    因此不能断言全局计数为 0，否则会被其它用例遗留数据污染。
    """
    with SessionLocal() as db:
        return db.scalar(
            select(func.count(PlanItem.id))
            .join(StudyPlan, StudyPlan.id == PlanItem.plan_id)
            .where(StudyPlan.user_id == user_id)
        )


def test_recommendations_do_not_write_plan_items(client):
    """建议是只读的：调用 /recommendations/today 不会为该用户写入任何计划项。"""
    ctx = _prepare(client)
    _answer(client, ctx["student"], ctx["question"]["id"], WRONG_ANSWER)
    _make_due(ctx["question"]["id"])

    user_id = ctx["student_user"]["id"]
    before = _plan_item_count(user_id)
    _today(client, ctx["student"])
    assert _plan_item_count(user_id) == before == 0


def test_recommendations_are_isolated_per_user(client):
    ctx = _prepare(client)
    _answer(client, ctx["student"], ctx["question"]["id"], WRONG_ANSWER)
    assert _today(client, ctx["student"])["items"]

    other = _register(client, "user")
    other_payload = _today(client, _headers(other))
    # 另一个用户没有任何作答 → 不应看到别人的薄弱点
    assert all(item["action"] != "review_weak" for item in other_payload["items"])
    assert all(item["action"] != "review_wrong" for item in other_payload["items"])


def test_legacy_question_without_knowledge_point_does_not_break(client):
    student = _register(client, "user")
    headers = _headers(student)
    question = _generate(client, headers)  # 不带 knowledge_point_id
    _answer(client, headers, question["id"], WRONG_ANSWER)
    _make_due(question["id"])
    payload = _today(client, headers)
    # legacy 题目没有结构化知识点 → 不硬塞、不报错
    assert payload["items"] == []


# ---------------------------------------------------------------- 目标加权
def test_goal_match_is_reflected_in_reason(client):
    ctx = _prepare(client)
    _set_goals(ctx["student_user"]["id"], "Mock Subject 期末冲刺")
    payload = _today(client, ctx["student"])
    item = payload["items"][0]
    assert "命中你的学习目标" in item["reason"]
    assert item["components"]["goal"] > 1.0


# ---------------------------------------------------------------- limit
def test_limit_is_respected_and_ordering_is_stable(client):
    admin = _register(client, "admin")
    headers = _headers(admin)
    for name in ("知识点A", "知识点B", "知识点C", "知识点D"):
        _create_kp(client, headers, name)
    student = _register(client, "user")
    payload = _today(client, _headers(student), limit=2)
    assert len(payload["items"]) == 2
    assert [item["order"] for item in payload["items"]] == [1, 2]
    scores = [item["score"] for item in payload["items"]]
    assert scores == sorted(scores, reverse=True)

    again = _today(client, _headers(student), limit=2)
    assert [item["knowledge_point_id"] for item in again["items"]] == [
        item["knowledge_point_id"] for item in payload["items"]
    ]


# ---------------------------------------------------------------- LLM 提议
def test_suggest_endpoint_only_proposes_and_never_writes(client):
    ctx = _prepare(client)
    with SessionLocal() as db:
        before = db.scalar(select(func.count(KnowledgePointPrerequisite.id)))

    response = client.post(
        f"{API}/knowledge-points/{ctx['advanced']['id']}/prerequisites/suggest",
        headers=ctx["admin"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["knowledge_point"]["id"] == ctx["advanced"]["id"]
    assert body["suggestions"] == []  # 离线/无效建议 → 空列表 + 提示语
    assert body["note"]

    with SessionLocal() as db:
        after = db.scalar(select(func.count(KnowledgePointPrerequisite.id)))
    assert after == before  # 提议绝不落库
