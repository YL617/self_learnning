"""大阶段 1 收尾：知识点「管理 → 选择 → 出题 → 结构化关联」产品化链路端到端验证。

覆盖：
- 管理员建点（层级、同学科父级、source 沿用后端默认）
- 前端选择器调用路径：按 subject 列出 / 名称搜索
- 出题携带 knowledge_point_id 生成 primary 结构化关联 + 反查
- 不传 knowledge_point_id 时 legacy 行为不变（无关联）
- 删除保护（存在子知识点 / 已被题目关联）与写权限

不新增 migration、不改造 question_knowledge_points、不修改历史 profile。
"""

import uuid

import pytest
from sqlalchemy import delete

from app.core.database import SessionLocal
from app.models import KnowledgePoint, Question, QuestionKnowledgePoint, User

API = "/api/v1"

# conftest 的 mock AI gateway 固定返回 subject="Mock Subject"。
# 生产环境中模型会回显请求学科，因此这里用同一学科建点，关联才能成立；
# 若学科不一致，落库题目的 subject 与知识点不一致会被整体回滚（见 Phase 2 原子性测试）。
AI_SUBJECT = "Mock Subject"


def _wipe() -> None:
    with SessionLocal() as db:
        db.execute(delete(QuestionKnowledgePoint))
        db.execute(delete(Question))
        db.execute(delete(KnowledgePoint))
        db.commit()


@pytest.fixture(autouse=True)
def _clean_productization_tables():
    _wipe()
    yield
    _wipe()


def _register(client, role: str = "user") -> dict:
    suffix = uuid.uuid4().hex[:10]
    response = client.post(
        f"{API}/auth/register",
        json={
            "email": f"prod_{suffix}@example.com",
            "username": f"prod_{suffix}",
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


def _create_kp(client, headers, name: str, subject: str = AI_SUBJECT, parent_id=None):
    payload = {"name": name, "subject": subject}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    response = client.post(f"{API}/knowledge-points", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _generate(
    client,
    headers,
    *,
    kp_name: str = "栈",
    subject: str = AI_SUBJECT,
    knowledge_point_id=None,
    count: int = 2,
):
    payload = {
        "subject": subject,
        "knowledge_point": kp_name,
        "count": count,
        "question_type": "choice",
    }
    if knowledge_point_id is not None:
        payload["knowledge_point_id"] = knowledge_point_id
    response = client.post(f"{API}/questions/generate", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_admin_creates_hierarchy_and_selector_queries(client):
    """管理员建点后，前端选择器按 subject / 名称查询可命中。"""
    admin = _register(client, "admin")
    headers = _headers(admin)

    root = _create_kp(client, headers, "线性表")
    # 表单不提交 source，后端沿用默认规则（admin）。
    assert root["source"] == "admin"
    assert root["status"] == "active"

    stack = _create_kp(client, headers, "栈", parent_id=root["id"])
    _create_kp(client, headers, "队列", parent_id=root["id"])
    assert stack["parent_id"] == root["id"]

    listed = client.get(f"{API}/knowledge-points", headers=headers, params={"subject": AI_SUBJECT})
    assert listed.status_code == 200
    assert [item["name"] for item in listed.json()] == ["线性表", "栈", "队列"]

    # 跨学科查询不应命中。
    other = client.get(f"{API}/knowledge-points", headers=headers, params={"subject": "操作系统"})
    assert other.json() == []

    searched = client.get(f"{API}/knowledge-points", headers=headers, params={"q": "栈"})
    assert [item["name"] for item in searched.json()] == ["栈"]


def test_parent_must_share_subject(client):
    admin = _register(client, "admin")
    headers = _headers(admin)
    root = _create_kp(client, headers, "线性表")
    foreign = _create_kp(client, headers, "进程", subject="操作系统")

    response = client.post(
        f"{API}/knowledge-points",
        headers=headers,
        json={"name": "栈", "subject": AI_SUBJECT, "parent_id": foreign["id"]},
    )
    assert response.status_code == 400
    assert root["id"] != foreign["id"]


def test_generate_with_knowledge_point_id_creates_primary_association(client):
    """出题带 knowledge_point_id → 生成 primary 结构化关联，且可反查题目。"""
    admin = _register(client, "admin")
    student = _register(client, "user")
    admin_headers = _headers(admin)
    student_headers = _headers(student)

    kp = _create_kp(client, admin_headers, "栈")
    questions = _generate(client, student_headers, knowledge_point_id=kp["id"], count=2)
    assert len(questions) == 2

    for question in questions:
        associations = client.get(
            f"{API}/questions/{question['id']}/knowledge-points", headers=student_headers
        ).json()
        assert len(associations) == 1
        assert associations[0]["knowledge_point_id"] == kp["id"]
        assert associations[0]["role"] == "primary"

    linked = client.get(
        f"{API}/knowledge-points/{kp['id']}/questions", headers=student_headers
    ).json()
    assert sorted(item["id"] for item in linked) == sorted(item["id"] for item in questions)


def test_generate_without_knowledge_point_id_keeps_legacy_behaviour(client):
    """不传 knowledge_point_id 时，出题行为与旧版一致：不产生结构化关联。"""
    student = _register(client, "user")
    headers = _headers(student)

    questions = _generate(client, headers, kp_name="栈和队列", count=1)
    associations = client.get(
        f"{API}/questions/{questions[0]['id']}/knowledge-points", headers=headers
    ).json()
    assert associations == []
    # 旧字段仍然保留，供列表回退展示。
    assert questions[0]["knowledge_point"]


def test_admin_update_then_delete_success(client):
    admin = _register(client, "admin")
    headers = _headers(admin)

    kp = _create_kp(client, headers, "栈")
    updated = client.patch(
        f"{API}/knowledge-points/{kp['id']}",
        headers=headers,
        json={"name": "栈结构", "status": "pending"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "栈结构"
    assert updated.json()["status"] == "pending"

    deleted = client.delete(f"{API}/knowledge-points/{kp['id']}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(f"{API}/knowledge-points", headers=headers).json() == []


def test_delete_blocked_by_children(client):
    admin = _register(client, "admin")
    headers = _headers(admin)

    root = _create_kp(client, headers, "线性表")
    _create_kp(client, headers, "栈", parent_id=root["id"])

    response = client.delete(f"{API}/knowledge-points/{root['id']}", headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "存在子知识点，无法删除"


def test_delete_blocked_when_question_linked(client):
    admin = _register(client, "admin")
    student = _register(client, "user")
    admin_headers = _headers(admin)

    kp = _create_kp(client, admin_headers, "栈")
    _generate(client, _headers(student), knowledge_point_id=kp["id"], count=1)

    response = client.delete(f"{API}/knowledge-points/{kp['id']}", headers=admin_headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "知识点已被题目关联，请先解除关联"


def test_non_admin_cannot_write(client):
    admin = _register(client, "admin")
    student = _register(client, "user")
    admin_headers = _headers(admin)
    student_headers = _headers(student)

    kp = _create_kp(client, admin_headers, "栈")

    create = client.post(
        f"{API}/knowledge-points",
        headers=student_headers,
        json={"name": "队列", "subject": AI_SUBJECT},
    )
    update = client.patch(
        f"{API}/knowledge-points/{kp['id']}", headers=student_headers, json={"name": "栈2"}
    )
    remove = client.delete(f"{API}/knowledge-points/{kp['id']}", headers=student_headers)
    assert (create.status_code, update.status_code, remove.status_code) == (403, 403, 403)

    # 普通用户仍可读取知识点（出题选择器需要）。
    readable = client.get(f"{API}/knowledge-points", headers=student_headers)
    assert readable.status_code == 200
    assert [item["name"] for item in readable.json()] == ["栈"]


def test_unauthenticated_write_rejected(client):
    response = client.post(f"{API}/knowledge-points", json={"name": "栈", "subject": AI_SUBJECT})
    assert response.status_code == 401
