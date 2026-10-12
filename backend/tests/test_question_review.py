"""M5.5 P4-2 题目审核生命周期 API 测试。

覆盖（用户批准的最小必要集）：
  1. 权限：全部审核端点对普通用户 403。
  2. 生命周期：draft→pending→approved→publish；pending→rejected。
  3. 非法转移：approve(draft) / publish(pending) / submit(approved) / archive(draft)
     / 终态 archived 一律 409。
  4. visibility 绕过禁止：编辑接口不接纳 visibility；发布只能经 publish。
  5. 编辑门禁：仅 draft/rejected 可编辑；pending/approved/archived 409。
  6. 审核留痕：approve 记录 reviewed_by/at 并清空旧 note；reject 写入 note。
  7. 列表过滤：review_status / visibility / subject。
  8. 404：对不存在题目的一切转移与编辑。
"""

import itertools

import pytest
from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.models import (
    AnswerRecord,
    KnowledgePoint,
    Question,
    QuestionKnowledgePoint,
    User,
    UserKnowledgePointMastery,
)


@pytest.fixture(autouse=True)
def _clean_tables():
    def _wipe() -> None:
        with SessionLocal() as db:
            db.execute(delete(UserKnowledgePointMastery))
            db.execute(delete(AnswerRecord))
            db.execute(delete(QuestionKnowledgePoint))
            db.execute(delete(Question))
            db.execute(delete(KnowledgePoint))
            db.commit()

    _wipe()
    yield
    _wipe()


_SEQ = itertools.count()


def _register(client, email: str, username: str) -> dict:
    local, _, domain = email.partition("@")
    seq = next(_SEQ)
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{local}.{seq}@{domain}",
            "username": f"{username}{seq}",
            "password": "123456",
        },
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


def _admin(client) -> dict:
    auth = _register(client, "m55rvadmin@test.com", "m55rvadmin")
    _set_role(auth, "admin")
    return auth


def _make_kp(name: str, subject: str = "数据结构") -> int:
    with SessionLocal() as db:
        kp = KnowledgePoint(
            name=name,
            normalized_name=name.lower(),
            subject=subject,
            normalized_subject=subject.lower(),
            node_type="concept",
        )
        db.add(kp)
        db.commit()
        return kp.id


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
        "visibility": "private",
    }
    payload.update(overrides)
    response = client.post("/api/v1/admin/questions", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _post(client, headers, question_id: int, action: str, json_body=None):
    return client.post(
        f"/api/v1/admin/questions/{question_id}/{action}",
        headers=headers,
        json=json_body if json_body is not None else {},
    )


# ---------- 1. 权限 ----------

def test_review_endpoints_require_admin(client):
    user = _register(client, "m55rvuser@test.com", "m55rvuser")
    headers = _headers(user)
    for action in (
        "submit-review",
        "approve",
        "reject",
        "publish",
        "archive",
    ):
        assert _post(client, headers, 1, action).status_code == 403
    assert (
        client.patch(
            "/api/v1/admin/questions/1", headers=headers, json={"stem": "x"}
        ).status_code
        == 403
    )


# ---------- 2. 生命周期 ----------

def test_admin_created_question_defaults_to_draft(client):
    admin = _admin(client)
    question = _create_question(client, _headers(admin))
    assert question["review_status"] == "draft"
    assert question["visibility"] == "private"


def test_draft_to_pending(client):
    admin = _admin(client)
    headers = _headers(admin)
    question = _create_question(client, headers)
    response = _post(client, headers, question["id"], "submit-review")
    assert response.status_code == 200
    assert response.json()["review_status"] == "pending"


def test_approve_records_reviewer_and_clears_note(client):
    admin = _admin(client)
    headers = _headers(admin)
    question = _create_question(client, headers)
    _post(client, headers, question["id"], "submit-review")
    # 先驳回留下 note
    _post(client, headers, question["id"], "reject", {"note": "解析缺失"})
    # 再提交 → 通过
    _post(client, headers, question["id"], "submit-review")
    response = _post(client, headers, question["id"], "approve")
    assert response.status_code == 200
    body = response.json()
    assert body["review_status"] == "approved"
    assert body["reviewed_by"] == admin["user"]["id"]
    assert body["reviewed_at"] is not None
    assert body["review_note"] is None  # approve 清空历史驳回意见


def test_reject_records_note(client):
    admin = _admin(client)
    headers = _headers(admin)
    question = _create_question(client, headers)
    _post(client, headers, question["id"], "submit-review")
    response = _post(
        client, headers, question["id"], "reject", {"note": "答案与解析矛盾"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["review_status"] == "rejected"
    assert body["review_note"] == "答案与解析矛盾"
    assert body["reviewed_by"] == admin["user"]["id"]


def test_full_happy_path_publish_sets_shared(client):
    admin = _admin(client)
    headers = _headers(admin)
    question = _create_question(client, headers)
    _post(client, headers, question["id"], "submit-review")
    _post(client, headers, question["id"], "approve")
    response = _post(client, headers, question["id"], "publish")
    assert response.status_code == 200
    body = response.json()
    assert body["visibility"] == "shared"
    assert body["review_status"] == "approved"
    # 详情复核：可见充要条件 shared ∧ approved 成立
    detail = client.get(
        f"/api/v1/admin/questions/{question['id']}", headers=headers
    ).json()
    assert detail["visibility"] == "shared"
    assert detail["review_status"] == "approved"


# ---------- 3. 非法转移 ----------

def test_illegal_transitions_return_409(client):
    admin = _admin(client)
    headers = _headers(admin)
    question = _create_question(client, headers)  # draft
    qid = question["id"]
    # draft 不能直接 approve / publish / reject / archive
    assert _post(client, headers, qid, "approve").status_code == 409
    assert _post(client, headers, qid, "publish").status_code == 409
    assert _post(client, headers, qid, "reject").status_code == 409
    assert _post(client, headers, qid, "archive").status_code == 409
    # → pending：不能再 submit，不能 publish
    _post(client, headers, qid, "submit-review")
    assert _post(client, headers, qid, "submit-review").status_code == 409
    assert _post(client, headers, qid, "publish").status_code == 409
    # → approved：不能再 approve / submit
    _post(client, headers, qid, "approve")
    assert _post(client, headers, qid, "approve").status_code == 409
    assert _post(client, headers, qid, "submit-review").status_code == 409
    # published → archive 合法，之后为终态
    assert _post(client, headers, qid, "publish").status_code == 200
    assert _post(client, headers, qid, "archive").status_code == 200
    assert _post(client, headers, qid, "submit-review").status_code == 409
    assert _post(client, headers, qid, "approve").status_code == 409
    assert _post(client, headers, qid, "publish").status_code == 409
    assert _post(client, headers, qid, "archive").status_code == 409


# ---------- 4. visibility 绕过禁止 ----------

def test_visibility_cannot_be_changed_via_patch(client):
    admin = _admin(client)
    headers = _headers(admin)
    question = _create_question(client, headers)  # private + draft
    # 意图绕过：在编辑体里塞 visibility —— 必须被忽略（接口无该字段）
    response = client.patch(
        f"/api/v1/admin/questions/{question['id']}",
        headers=headers,
        json={"stem": "新题干", "visibility": "shared"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["stem"] == "新题干"
    assert body["visibility"] == "private"  # 未被改动
    assert body["review_status"] == "draft"

    # 未过审也无法发布
    assert _post(client, headers, question["id"], "publish").status_code == 409


# ---------- 5. 编辑门禁 ----------

def test_edit_only_allowed_in_draft_or_rejected(client):
    admin = _admin(client)
    headers = _headers(admin)
    question = _create_question(client, headers)
    qid = question["id"]
    url = f"/api/v1/admin/questions/{qid}"

    # draft 可编辑
    assert client.patch(url, headers=headers, json={"answer": "A"}).status_code == 200

    # pending 不可编辑
    _post(client, headers, qid, "submit-review")
    assert client.patch(url, headers=headers, json={"answer": "A"}).status_code == 409

    # rejected 可编辑
    _post(client, headers, qid, "reject", {"note": "改答案"})
    assert client.patch(url, headers=headers, json={"answer": "A"}).status_code == 200

    # approved 不可编辑
    _post(client, headers, qid, "submit-review")
    _post(client, headers, qid, "approve")
    assert client.patch(url, headers=headers, json={"answer": "B"}).status_code == 409

    # archived 不可编辑
    _post(client, headers, qid, "archive")
    assert client.patch(url, headers=headers, json={"answer": "B"}).status_code == 409


def test_patch_updates_options_and_difficulty(client):
    admin = _admin(client)
    headers = _headers(admin)
    question = _create_question(client, headers)
    response = client.patch(
        f"/api/v1/admin/questions/{question['id']}",
        headers=headers,
        json={"options": ["A. 1", "B. 2"], "difficulty": "hard"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["difficulty"] == "hard"
    with SessionLocal() as db:
        row = db.get(Question, question["id"])
        assert row.options_json == '["A. 1", "B. 2"]'


# ---------- 6. 列表过滤 ----------

def test_list_admin_questions_filters(client):
    admin = _admin(client)
    headers = _headers(admin)
    d = _create_question(client, headers, stem="草稿题")
    p = _create_question(client, headers, stem="待审题", subject="操作系统")
    _post(client, headers, d["id"], "submit-review")
    _post(client, headers, p["id"], "submit-review")
    _post(client, headers, p["id"], "approve")
    _post(client, headers, p["id"], "publish")

    base = client.get("/api/v1/admin/questions", headers=headers).json()
    assert {q["id"] for q in base} >= {d["id"], p["id"]}

    pending = client.get(
        "/api/v1/admin/questions", headers=headers, params={"review_status": "pending"}
    ).json()
    assert {q["id"] for q in pending} == {d["id"]}

    approved = client.get(
        "/api/v1/admin/questions", headers=headers, params={"review_status": "approved"}
    ).json()
    assert {q["id"] for q in approved} == {p["id"]}

    shared = client.get(
        "/api/v1/admin/questions", headers=headers, params={"visibility": "shared"}
    ).json()
    assert {q["id"] for q in shared} == {p["id"]}

    by_subject = client.get(
        "/api/v1/admin/questions", headers=headers, params={"subject": "操作系统"}
    ).json()
    assert {q["id"] for q in by_subject} == {p["id"]}

    # 非法过滤值被 422 拒绝（pattern 校验）
    assert (
        client.get(
            "/api/v1/admin/questions",
            headers=headers,
            params={"review_status": "bogus"},
        ).status_code
        == 422
    )


# ---------- 7. 404 ----------

def test_review_on_missing_question_404(client):
    admin = _admin(client)
    headers = _headers(admin)
    assert _post(client, headers, 999999, "submit-review").status_code == 404
    assert _post(client, headers, 999999, "approve").status_code == 404
    assert _post(client, headers, 999999, "publish").status_code == 404
    assert (
        client.patch(
            "/api/v1/admin/questions/999999", headers=headers, json={"stem": "x"}
        ).status_code
        == 404
    )


# ---------- 8. 与既有 M4 共享题逻辑不冲突 ----------

def test_publish_does_not_touch_other_questions(client):
    admin = _admin(client)
    headers = _headers(admin)
    q1 = _create_question(client, headers, stem="问题一")
    q2 = _create_question(client, headers, stem="问题二")
    _post(client, headers, q1["id"], "submit-review")
    _post(client, headers, q1["id"], "approve")
    _post(client, headers, q1["id"], "publish")
    with SessionLocal() as db:
        other = db.get(Question, q2["id"])
        assert other.visibility == "private"
        assert other.review_status == "draft"
        published = db.scalar(select(Question).where(Question.id == q1["id"]))
        assert published.visibility == "shared"
