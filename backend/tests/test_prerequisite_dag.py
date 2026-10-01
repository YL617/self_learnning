"""大阶段 3：知识点前置依赖（DAG）单元测试。

覆盖：纯图算法（传递前置 / 解锁统计 / 拓扑序）与写入校验（自环 / 成环 / 重复 / 越权）。
纯图算法部分直接把边表传进去，不依赖数据库，因此可以在无 DB 的情况下精确断言。
"""

import uuid

import pytest
from sqlalchemy import delete

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
from app.services.prerequisite import (
    BLOCKING_STRENGTH,
    READY_THRESHOLD,
    PrerequisiteService,
)

API = "/api/v1"

# 图：(后置, 前置) —— 树依赖链表；二叉树依赖树；平衡树依赖二叉树 与 树
CHAIN_EDGES = [(2, 1), (3, 2), (4, 3)]
DIAMOND_EDGES = [(2, 1), (3, 1), (4, 2), (4, 3)]  # 1 是根；4 同时依赖 2 和 3


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


def _graph(pairs=None) -> PrerequisiteService:
    """纯图测试用：不触碰数据库（所有方法都显式传入 pairs）。"""
    return PrerequisiteService(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------- 纯图算法
def test_prerequisite_closure_is_transitive():
    service = _graph()
    assert service.prerequisite_closure(4, pairs=CHAIN_EDGES) == {1, 2, 3}
    assert service.prerequisite_closure(1, pairs=CHAIN_EDGES) == set()
    assert service.prerequisite_closure(2, pairs=CHAIN_EDGES) == {1}


def test_prerequisite_closure_handles_diamond_without_duplicates():
    service = _graph()
    assert service.prerequisite_closure(4, pairs=DIAMOND_EDGES) == {1, 2, 3}


def test_unlock_count_counts_transitive_dependents():
    service = _graph()
    # 解锁统计 = 传递后置数量（跨层去重）
    assert service.unlock_count(1, pairs=DIAMOND_EDGES) == 3
    assert service.unlock_count(2, pairs=DIAMOND_EDGES) == 1
    assert service.unlock_count(4, pairs=DIAMOND_EDGES) == 0


def test_unlock_count_ignores_self_when_cyclic():
    service = _graph()
    # 异常图（理论上写入层已拦截）：不能把自己算成"被解锁"
    assert service.unlock_count(1, pairs=[(2, 1), (1, 2)]) == 1


def test_topological_order_puts_prerequisites_first():
    service = _graph()
    assert service.topological_order({1, 2, 3, 4}, pairs=CHAIN_EDGES) == [1, 2, 3, 4]
    assert service.topological_order({4, 3, 2, 1}, pairs=DIAMOND_EDGES) == [1, 2, 3, 4]


def test_topological_order_is_deterministic_for_siblings():
    service = _graph()
    first = service.topological_order({1, 2, 3, 4}, pairs=DIAMOND_EDGES)
    second = service.topological_order({4, 2, 1, 3}, pairs=DIAMOND_EDGES)
    assert first == second == [1, 2, 3, 4]


def test_topological_order_always_returns_every_node_on_cycle():
    service = _graph()
    ordered = service.topological_order({1, 2, 3}, pairs=[(1, 2), (2, 1)])
    assert sorted(ordered) == [1, 2, 3]


def test_statuses_treat_unknown_mastery_as_unsatisfied():
    from app.services.prerequisite import evaluate_statuses

    edges = [(1, 100), (2, 30)]
    statuses = evaluate_statuses(edges, {}, threshold=READY_THRESHOLD)
    assert [(s.prerequisite_id, s.satisfied, s.blocking) for s in statuses] == [
        (1, False, True),  # 无记录 + 硬前置 → 阻塞
        (2, False, False),  # 无记录 + 软前置 → 不阻塞
    ]
    relaxed = evaluate_statuses(edges, {1: 90, 2: 10}, threshold=READY_THRESHOLD)
    assert [s.blocking for s in relaxed] == [False, False]


def test_soft_prerequisite_above_threshold_is_satisfied():
    from app.services.prerequisite import evaluate_statuses

    statuses = evaluate_statuses([(1, BLOCKING_STRENGTH)], {1: READY_THRESHOLD})
    assert statuses[0].satisfied is True
    assert statuses[0].blocking is False


# ---------------------------------------------------------------- API 校验
def _register(client, role: str = "user") -> dict:
    suffix = uuid.uuid4().hex[:10]
    response = client.post(
        f"{API}/auth/register",
        json={
            "email": f"pre_{suffix}@example.com",
            "username": f"pre_{suffix}",
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


def _create_kp(client, headers, name: str, subject: str = "数据结构") -> dict:
    response = client.post(
        f"{API}/knowledge-points", headers=headers, json={"name": name, "subject": subject}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _add_edge(client, headers, dependent_id: int, prerequisite_id: int, **extra):
    return client.post(
        f"{API}/knowledge-points/{dependent_id}/prerequisites",
        headers=headers,
        json={"prerequisite_id": prerequisite_id, **extra},
    )


def test_admin_can_add_and_list_prerequisite(client):
    admin = _register(client, "admin")
    headers = _headers(admin)
    linked = _create_kp(client, headers, "链表")
    tree = _create_kp(client, headers, "树")

    response = _add_edge(client, headers, tree["id"], linked["id"], strength=80, note="先学链表")
    assert response.status_code == 201, response.text
    edge = response.json()
    assert edge["knowledge_point_id"] == tree["id"]
    assert edge["prerequisite_id"] == linked["id"]
    assert edge["strength"] == 80
    assert edge["source"] == "manual"
    assert edge["status"] == "active"
    assert edge["prerequisite"]["name"] == "链表"

    listing = client.get(
        f"{API}/knowledge-points/{tree['id']}/prerequisites", headers=headers
    )
    assert listing.status_code == 200, listing.text
    payload = listing.json()
    assert payload["threshold"] == READY_THRESHOLD
    assert payload["ready"] is False  # 管理员本身没有掌握度记录 → 前置未满足
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["satisfied"] is False
    assert item["blocking"] is True  # strength 80 >= BLOCKING_STRENGTH


def test_low_strength_prerequisite_is_not_blocking(client):
    admin = _register(client, "admin")
    headers = _headers(admin)
    base = _create_kp(client, headers, "数组")
    advanced = _create_kp(client, headers, "动态规划")
    assert (
        _add_edge(
            client, headers, advanced["id"], base["id"], strength=BLOCKING_STRENGTH - 1
        ).status_code
        == 201
    )
    payload = client.get(
        f"{API}/knowledge-points/{advanced['id']}/prerequisites", headers=headers
    ).json()
    assert payload["items"][0]["satisfied"] is False
    assert payload["items"][0]["blocking"] is False
    assert payload["ready"] is True  # 软前置未满足不阻塞


def test_self_loop_is_rejected(client):
    admin = _register(client, "admin")
    headers = _headers(admin)
    kp = _create_kp(client, headers, "栈")
    response = _add_edge(client, headers, kp["id"], kp["id"])
    assert response.status_code == 400, response.text
    assert "自己" in response.json()["detail"]


def test_cycle_is_rejected(client):
    admin = _register(client, "admin")
    headers = _headers(admin)
    a = _create_kp(client, headers, "链表")
    b = _create_kp(client, headers, "树")
    c = _create_kp(client, headers, "二叉树")

    assert _add_edge(client, headers, b["id"], a["id"]).status_code == 201
    assert _add_edge(client, headers, c["id"], b["id"]).status_code == 201
    # c → a → b → c 会成环
    response = _add_edge(client, headers, a["id"], c["id"])
    assert response.status_code == 400, response.text
    assert "循环" in response.json()["detail"]


def test_duplicate_edge_is_rejected(client):
    admin = _register(client, "admin")
    headers = _headers(admin)
    a = _create_kp(client, headers, "A")
    b = _create_kp(client, headers, "B")
    assert _add_edge(client, headers, b["id"], a["id"]).status_code == 201
    response = _add_edge(client, headers, b["id"], a["id"])
    assert response.status_code == 409, response.text


def test_missing_knowledge_point_is_404(client):
    admin = _register(client, "admin")
    headers = _headers(admin)
    a = _create_kp(client, headers, "A")
    assert _add_edge(client, headers, a["id"], 999999).status_code == 404
    assert _add_edge(client, headers, 999999, a["id"]).status_code == 404
    assert (
        client.get(f"{API}/knowledge-points/999999/prerequisites", headers=headers).status_code
        == 404
    )
    assert (
        client.get(f"{API}/knowledge-points/999999/path", headers=headers).status_code == 404
    )


def test_delete_prerequisite_edge(client):
    admin = _register(client, "admin")
    headers = _headers(admin)
    a = _create_kp(client, headers, "A")
    b = _create_kp(client, headers, "B")
    assert _add_edge(client, headers, b["id"], a["id"]).status_code == 201

    response = client.delete(
        f"{API}/knowledge-points/{b['id']}/prerequisites/{a['id']}", headers=headers
    )
    assert response.status_code == 204, response.text
    assert (
        client.get(f"{API}/knowledge-points/{b['id']}/prerequisites", headers=headers).json()[
            "items"
        ]
        == []
    )
    again = client.delete(
        f"{API}/knowledge-points/{b['id']}/prerequisites/{a['id']}", headers=headers
    )
    assert again.status_code == 404


def test_non_admin_cannot_manage_prerequisites(client):
    admin = _register(client, "admin")
    student = _register(client, "user")
    admin_headers = _headers(admin)
    student_headers = _headers(student)
    a = _create_kp(client, admin_headers, "A")
    b = _create_kp(client, admin_headers, "B")

    assert _add_edge(client, student_headers, b["id"], a["id"]).status_code == 403
    assert (
        client.delete(
            f"{API}/knowledge-points/{b['id']}/prerequisites/{a['id']}",
            headers=student_headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{API}/knowledge-points/{b['id']}/prerequisites/suggest",
            headers=student_headers,
        ).status_code
        == 403
    )


def test_learning_path_returns_topological_order(client):
    admin = _register(client, "admin")
    headers = _headers(admin)
    linked = _create_kp(client, headers, "链表")
    tree = _create_kp(client, headers, "树")
    binary = _create_kp(client, headers, "二叉树")
    assert _add_edge(client, headers, tree["id"], linked["id"]).status_code == 201
    assert _add_edge(client, headers, binary["id"], tree["id"]).status_code == 201

    response = client.get(
        f"{API}/knowledge-points/{binary['id']}/path", headers=headers
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert [step["knowledge_point"]["name"] for step in payload["steps"]] == [
        "链表",
        "树",
        "二叉树",
    ]
    assert payload["steps"][-1]["is_target"] is True
    assert [step["order"] for step in payload["steps"]] == [1, 2, 3]
    assert payload["threshold"] == READY_THRESHOLD

    isolated = client.get(f"{API}/knowledge-points/{linked['id']}/path", headers=headers).json()
    assert [step["knowledge_point"]["name"] for step in isolated["steps"]] == ["链表"]


def test_delete_knowledge_point_blocked_by_prerequisite_edges(client):
    admin = _register(client, "admin")
    headers = _headers(admin)
    a = _create_kp(client, headers, "A")
    b = _create_kp(client, headers, "B")
    assert _add_edge(client, headers, b["id"], a["id"]).status_code == 201

    response = client.delete(f"{API}/knowledge-points/{b['id']}", headers=headers)
    assert response.status_code == 400, response.text
    assert "前置依赖" in response.json()["detail"]

    # 解除后置关系后即可删除
    assert (
        client.delete(
            f"{API}/knowledge-points/{b['id']}/prerequisites/{a['id']}", headers=headers
        ).status_code
        == 204
    )
    assert client.delete(f"{API}/knowledge-points/{b['id']}", headers=headers).status_code == 204


def test_edges_persist_and_read_back(client):
    """服务层直连：边落库后 PrerequisiteService 能读回同样的图。"""
    admin = _register(client, "admin")
    headers = _headers(admin)
    a = _create_kp(client, headers, "A")
    b = _create_kp(client, headers, "B")
    assert _add_edge(client, headers, b["id"], a["id"]).status_code == 201

    with SessionLocal() as db:
        service = PrerequisiteService(db)
        assert service.edge_pairs() == [(b["id"], a["id"])]
        assert service.unlock_count(a["id"]) == 1
        assert service.has_edges(a["id"]) is True
        assert service.has_edges(b["id"]) is True
