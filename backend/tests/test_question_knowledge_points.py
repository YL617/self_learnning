"""Phase 2：题目 ↔ 知识点结构化关联的完整测试。

覆盖 Service 不变量、API 权限、generate 兼容、legacy backfill、
Question 删除级联与 KnowledgePoint 删除保护。
"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from backfill_question_knowledge_points import build_index, plan_backfill

from app.core.database import SessionLocal
from app.models import (
    KnowledgePoint,
    Question,
    QuestionKnowledgePoint,
    User,
)


@pytest.fixture(autouse=True)
def _clean_phase2_tables():
    with SessionLocal() as db:
        db.execute(delete(QuestionKnowledgePoint))
        db.execute(delete(Question))
        db.execute(delete(KnowledgePoint))
        db.commit()
    yield
    with SessionLocal() as db:
        db.execute(delete(QuestionKnowledgePoint))
        db.execute(delete(Question))
        db.execute(delete(KnowledgePoint))
        db.commit()


def _register(client, email: str, username: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": username, "password": "123456"},
    )
    assert response.status_code == 201
    return response.json()


def _headers(auth: dict) -> dict:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _set_role(auth: dict, role: str) -> None:
    with SessionLocal() as db:
        user = db.get(User, auth["user"]["id"])
        user.role = role
        db.commit()


def _make_knowledge_point(name: str, subject: str) -> int:
    with SessionLocal() as db:
        kp = KnowledgePoint(
            name=name,
            normalized_name=name.lower(),
            subject=subject,
            normalized_subject=subject.lower(),
        )
        db.add(kp)
        db.commit()
        return kp.id


def _make_question(user_id: int, subject: str = "数据结构", text: str = "栈") -> int:
    with SessionLocal() as db:
        question = Question(
            user_id=user_id,
            subject=subject,
            knowledge_point=text,
            question_type="choice",
            stem="s",
            answer="a",
            source="ai",
        )
        db.add(question)
        db.commit()
        return question.id


def _generate(client, headers, *, subject="数据结构", kp="栈和队列", count=2,
             knowledge_point_id=None, expect=201):
    payload = {"subject": subject, "knowledge_point": kp, "count": count}
    if knowledge_point_id is not None:
        payload["knowledge_point_id"] = knowledge_point_id
    response = client.post("/api/v1/questions/generate", headers=headers, json=payload)
    assert response.status_code == expect, response.text
    return response


# ---------- Service / API 基础 ----------


def test_attach_primary_success(client):
    owner = _register(client, "p2a@example.com", "p2a")
    qid = _make_question(owner["user"]["id"])
    kp_id = _make_knowledge_point("栈和队列", "数据结构")
    response = client.post(
        f"/api/v1/questions/{qid}/knowledge-points",
        headers=_headers(owner),
        json={"knowledge_point_id": kp_id, "role": "primary"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["role"] == "primary"
    assert body["source"] == "manual"
    assert body["question_id"] == qid
    assert body["knowledge_point_id"] == kp_id


def test_attach_secondary_success(client):
    owner = _register(client, "p2b@example.com", "p2b")
    qid = _make_question(owner["user"]["id"])
    primary = _make_knowledge_point("栈", "数据结构")
    secondary = _make_knowledge_point("队列", "数据结构")
    h = _headers(owner)
    assert client.post(
        f"/api/v1/questions/{qid}/knowledge-points", headers=h,
        json={"knowledge_point_id": primary},
    ).status_code == 201
    response = client.post(
        f"/api/v1/questions/{qid}/knowledge-points", headers=h,
        json={"knowledge_point_id": secondary, "role": "secondary"},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "secondary"


def test_duplicate_attach_is_idempotent(client):
    owner = _register(client, "p2c@example.com", "p2c")
    qid = _make_question(owner["user"]["id"])
    kp_id = _make_knowledge_point("栈和队列", "数据结构")
    h = _headers(owner)
    first = client.post(
        f"/api/v1/questions/{qid}/knowledge-points", headers=h,
        json={"knowledge_point_id": kp_id},
    )
    second = client.post(
        f"/api/v1/questions/{qid}/knowledge-points", headers=h,
        json={"knowledge_point_id": kp_id},
    )
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    with SessionLocal() as db:
        count = db.scalar(
            select(func.count()).select_from(QuestionKnowledgePoint)
        )
    assert count == 1


def test_second_primary_attach_conflicts(client):
    owner = _register(client, "p2d@example.com", "p2d")
    qid = _make_question(owner["user"]["id"])
    kp1 = _make_knowledge_point("栈", "数据结构")
    kp2 = _make_knowledge_point("队列", "数据结构")
    h = _headers(owner)
    assert client.post(
        f"/api/v1/questions/{qid}/knowledge-points", headers=h,
        json={"knowledge_point_id": kp1},
    ).status_code == 201
    response = client.post(
        f"/api/v1/questions/{qid}/knowledge-points", headers=h,
        json={"knowledge_point_id": kp2, "role": "primary"},
    )
    assert response.status_code == 400
    assert "主要知识点" in response.json()["detail"]


def test_set_primary_demotes_old_primary(client):
    owner = _register(client, "p2e@example.com", "p2e")
    qid = _make_question(owner["user"]["id"])
    kp1 = _make_knowledge_point("栈", "数据结构")
    kp2 = _make_knowledge_point("队列", "数据结构")
    h = _headers(owner)
    for kp in (kp1, kp2):
        client.post(
            f"/api/v1/questions/{qid}/knowledge-points", headers=h,
            json={"knowledge_point_id": kp, "role": "secondary"},
        )
    response = client.patch(
        f"/api/v1/questions/{qid}/knowledge-points/{kp2}", headers=_headers(owner)
    )
    assert response.status_code == 200
    assert response.json()["role"] == "primary"
    listed = client.get(f"/api/v1/questions/{qid}/knowledge-points", headers=h).json()
    roles = {row["knowledge_point_id"]: row["role"] for row in listed}
    assert roles == {kp1: "secondary", kp2: "primary"}


def test_set_primary_without_association_404(client):
    owner = _register(client, "p2f@example.com", "p2f")
    qid = _make_question(owner["user"]["id"])
    kp_id = _make_knowledge_point("栈", "数据结构")
    response = client.patch(
        f"/api/v1/questions/{qid}/knowledge-points/{kp_id}", headers=_headers(owner)
    )
    assert response.status_code == 404


@pytest.mark.parametrize("roles,expect", [
    ([], 200),
    ([("栈", "secondary")], 200),
    ([("栈", "primary"), ("队列", "secondary")], 200),
])
def test_replace_allows_zero_or_one_primary(client, roles, expect):
    owner = _register(client, f"p2g{expect}{len(roles)}@example.com",
                      f"p2g{expect}{len(roles)}")
    qid = _make_question(owner["user"]["id"])
    ids = {name: _make_knowledge_point(name, "数据结构") for name, _ in roles}
    payload = {"items": [
        {"knowledge_point_id": ids[name], "role": role} for name, role in roles
    ]}
    response = client.put(
        f"/api/v1/questions/{qid}/knowledge-points",
        headers=_headers(owner), json=payload,
    )
    assert response.status_code == expect
    if expect == 200:
        returned = response.json()
        assert len(returned) == len(roles)
        primaries = [row for row in returned if row["role"] == "primary"]
        assert len(primaries) <= 1


def test_replace_with_two_primaries_conflicts(client):
    owner = _register(client, "p2h@example.com", "p2h")
    qid = _make_question(owner["user"]["id"])
    kp1 = _make_knowledge_point("栈", "数据结构")
    kp2 = _make_knowledge_point("队列", "数据结构")
    response = client.put(
        f"/api/v1/questions/{qid}/knowledge-points",
        headers=_headers(owner),
        json={"items": [
            {"knowledge_point_id": kp1, "role": "primary"},
            {"knowledge_point_id": kp2, "role": "primary"},
        ]},
    )
    assert response.status_code == 400


def test_replace_removes_dropped_associations(client):
    owner = _register(client, "p2i@example.com", "p2i")
    qid = _make_question(owner["user"]["id"])
    kp1 = _make_knowledge_point("栈", "数据结构")
    kp2 = _make_knowledge_point("队列", "数据结构")
    h = _headers(owner)
    client.put(
        f"/api/v1/questions/{qid}/knowledge-points", headers=h,
        json={"items": [{"knowledge_point_id": kp1}, {"knowledge_point_id": kp2}]},
    )
    response = client.put(
        f"/api/v1/questions/{qid}/knowledge-points", headers=h,
        json={"items": [{"knowledge_point_id": kp1}]},
    )
    assert response.status_code == 200
    assert [row["knowledge_point_id"] for row in response.json()] == [kp1]


def test_detach_success_and_missing(client):
    owner = _register(client, "p2j@example.com", "p2j")
    qid = _make_question(owner["user"]["id"])
    kp_id = _make_knowledge_point("栈", "数据结构")
    h = _headers(owner)
    client.post(
        f"/api/v1/questions/{qid}/knowledge-points", headers=h,
        json={"knowledge_point_id": kp_id},
    )
    assert client.delete(
        f"/api/v1/questions/{qid}/knowledge-points/{kp_id}", headers=h
    ).status_code == 204
    assert client.get(f"/api/v1/questions/{qid}/knowledge-points", headers=h).json() == []
    assert client.delete(
        f"/api/v1/questions/{qid}/knowledge-points/{kp_id}", headers=h
    ).status_code == 404


def test_multiple_points_on_one_question_and_multiple_questions_per_point(client):
    owner = _register(client, "p2k@example.com", "p2k")
    uid = owner["user"]["id"]
    q1 = _make_question(uid)
    q2 = _make_question(uid)
    kp1 = _make_knowledge_point("栈", "数据结构")
    kp2 = _make_knowledge_point("队列", "数据结构")
    h = _headers(owner)
    for qid, kp in ((q1, kp1), (q1, kp2), (q2, kp1)):
        assert client.post(
            f"/api/v1/questions/{qid}/knowledge-points", headers=h,
            json={"knowledge_point_id": kp, "role": "secondary"},
        ).status_code == 201
    assert len(client.get(f"/api/v1/questions/{q1}/knowledge-points", headers=h).json()) == 2
    assert len(client.get(f"/api/v1/questions/{q2}/knowledge-points", headers=h).json()) == 1


def test_question_not_found(client):
    owner = _register(client, "p2l@example.com", "p2l")
    response = client.get(
        "/api/v1/questions/999999/knowledge-points", headers=_headers(owner)
    )
    assert response.status_code == 404


def test_knowledge_point_not_found(client):
    owner = _register(client, "p2m@example.com", "p2m")
    qid = _make_question(owner["user"]["id"])
    response = client.post(
        f"/api/v1/questions/{qid}/knowledge-points",
        headers=_headers(owner),
        json={"knowledge_point_id": 999999},
    )
    assert response.status_code == 404


def test_subject_mismatch_rejected(client):
    owner = _register(client, "p2n@example.com", "p2n")
    qid = _make_question(owner["user"]["id"], subject="数据结构")
    kp_id = _make_knowledge_point("操作系统", "计算机组成")
    response = client.post(
        f"/api/v1/questions/{qid}/knowledge-points",
        headers=_headers(owner),
        json={"knowledge_point_id": kp_id},
    )
    assert response.status_code == 400
    assert "学科" in response.json()["detail"]


# ---------- 权限与泄漏防护 ----------


def test_other_user_gets_404_on_foreign_question(client):
    owner = _register(client, "p2o@example.com", "p2o")
    other = _register(client, "p2p@example.com", "p2p")
    uid = owner["user"]["id"]
    qid = _make_question(uid)
    kp_id = _make_knowledge_point("栈", "数据结构")
    oh = _headers(owner)
    client.post(
        f"/api/v1/questions/{qid}/knowledge-points", headers=oh,
        json={"knowledge_point_id": kp_id},
    )
    fh = _headers(other)
    assert client.get(f"/api/v1/questions/{qid}/knowledge-points", headers=fh).status_code == 404
    assert client.post(
        f"/api/v1/questions/{qid}/knowledge-points", headers=fh,
        json={"knowledge_point_id": kp_id},
    ).status_code == 404
    assert client.patch(
        f"/api/v1/questions/{qid}/knowledge-points/{kp_id}", headers=fh
    ).status_code == 404
    assert client.delete(
        f"/api/v1/questions/{qid}/knowledge-points/{kp_id}", headers=fh
    ).status_code == 404


def test_admin_can_manage_foreign_question(client):
    owner = _register(client, "p2q@example.com", "p2q")
    admin = _register(client, "p2r@example.com", "p2r")
    _set_role(admin, "admin")
    qid = _make_question(owner["user"]["id"])
    kp_id = _make_knowledge_point("栈", "数据结构")
    ah = _headers(admin)
    assert client.post(
        f"/api/v1/questions/{qid}/knowledge-points", headers=ah,
        json={"knowledge_point_id": kp_id},
    ).status_code == 201
    listed = client.get(f"/api/v1/questions/{qid}/knowledge-points", headers=ah)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert client.patch(
        f"/api/v1/questions/{qid}/knowledge-points/{kp_id}", headers=ah
    ).status_code == 200
    assert client.delete(
        f"/api/v1/questions/{qid}/knowledge-points/{kp_id}", headers=ah
    ).status_code == 204


def test_reverse_lookup_owner_filter_no_leak(client):
    owner = _register(client, "p2s@example.com", "p2s")
    stranger = _register(client, "p2t@example.com", "p2t")
    admin = _register(client, "p2u@example.com", "p2u")
    _set_role(admin, "admin")
    uid = owner["user"]["id"]
    qid = _make_question(uid)
    kp_id = _make_knowledge_point("栈", "数据结构")
    oh = _headers(owner)
    client.post(
        f"/api/v1/questions/{qid}/knowledge-points", headers=oh,
        json={"knowledge_point_id": kp_id},
    )
    # 普通用户（他人）看不到别人的题目
    assert client.get(
        f"/api/v1/knowledge-points/{kp_id}/questions", headers=_headers(stranger)
    ).json() == []
    # owner 只看到自己的
    owner_view = client.get(
        f"/api/v1/knowledge-points/{kp_id}/questions", headers=oh
    ).json()
    assert [row["id"] for row in owner_view] == [qid]
    # 管理员可见全部
    admin_view = client.get(
        f"/api/v1/knowledge-points/{kp_id}/questions", headers=_headers(admin)
    ).json()
    assert [row["id"] for row in admin_view] == [qid]


# ---------- KnowledgePoint 删除保护 / Question 级联 ----------


def test_knowledge_point_delete_blocked_when_linked(client):
    owner = _register(client, "p2v@example.com", "p2v")
    admin = _register(client, "p2w@example.com", "p2w")
    _set_role(admin, "admin")
    qid = _make_question(owner["user"]["id"])
    kp_id = _make_knowledge_point("栈", "数据结构")
    client.post(
        f"/api/v1/questions/{qid}/knowledge-points", headers=_headers(owner),
        json={"knowledge_point_id": kp_id},
    )
    response = client.delete(f"/api/v1/knowledge-points/{kp_id}", headers=_headers(admin))
    assert response.status_code == 400
    assert "题目关联" in response.json()["detail"]
    # 解除关联后可删除
    client.delete(
        f"/api/v1/questions/{qid}/knowledge-points/{kp_id}", headers=_headers(owner)
    )
    assert client.delete(
        f"/api/v1/knowledge-points/{kp_id}", headers=_headers(admin)
    ).status_code == 204


def test_question_delete_cascades_associations(client):
    owner = _register(client, "p2x@example.com", "p2x")
    uid = owner["user"]["id"]
    qid = _make_question(uid)
    kp_id = _make_knowledge_point("栈", "数据结构")
    client.post(
        f"/api/v1/questions/{qid}/knowledge-points", headers=_headers(owner),
        json={"knowledge_point_id": kp_id},
    )
    assert client.delete(f"/api/v1/questions/{qid}", headers=_headers(owner)).status_code == 204
    with SessionLocal() as db:
        count = db.scalar(
            select(func.count()).select_from(QuestionKnowledgePoint).where(
                QuestionKnowledgePoint.question_id == qid
            )
        )
    assert count == 0


# ---------- generate 兼容 ----------


def test_generate_without_kp_id_keeps_legacy_behavior(client):
    owner = _register(client, "p2y@example.com", "p2y")
    _generate(client, _headers(owner))
    with SessionLocal() as db:
        rows = list(db.scalars(select(Question)).all())
    assert len(rows) == 2
    assert all(row.knowledge_point == "Mock Point" for row in rows)
    assert db.scalar(select(func.count()).select_from(QuestionKnowledgePoint)) == 0


def test_generate_with_valid_kp_id_creates_primary_link(client):
    owner = _register(client, "p2z@example.com", "p2z")
    kp_id = _make_knowledge_point("Mock Point", "Mock Subject")
    _generate(client, _headers(owner), subject="Mock Subject", kp="任意文本",
              knowledge_point_id=kp_id)
    with SessionLocal() as db:
        rows = list(db.scalars(select(QuestionKnowledgePoint)).all())
    assert len(rows) == 2
    assert {row.role for row in rows} == {"primary"}
    assert {row.source for row in rows} == {"manual"}
    assert {row.knowledge_point_id for row in rows} == {kp_id}


def test_generate_kp_subject_mismatch_rejected(client):
    owner = _register(client, "p2aa@example.com", "p2aa")
    kp_id = _make_knowledge_point("操作系统", "别的学科")
    before = _count_questions()
    _generate(client, _headers(owner), knowledge_point_id=kp_id, expect=400)
    assert _count_questions() == before


def test_generate_kp_missing_rejected(client):
    owner = _register(client, "p2ab@example.com", "p2ab")
    before = _count_questions()
    _generate(client, _headers(owner), knowledge_point_id=999999, expect=404)
    assert _count_questions() == before


def test_generate_atomic_no_half_created_question(client):
    """前置校验通过、但 AI 返回学科偏离时，关联失败必须整体回滚。"""
    owner = _register(client, "p2ac@example.com", "p2ac")
    kp_id = _make_knowledge_point("栈和队列", "数据结构")
    before = _count_questions()
    # 请求 subject 与 KP 一致（前置校验通过），但 mock AI 返回 "Mock Subject"，
    # 落库题目的 subject 与 KP 不一致 → attach 失败 → 整个事务回滚。
    _generate(client, _headers(owner), subject="数据结构",
              knowledge_point_id=kp_id, expect=400)
    assert _count_questions() == before


def _count_questions() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(Question))


# ---------- legacy backfill（纯函数 plan_backfill） ----------


class _Row:
    def __init__(self, qid=None, subject="", text="", kp_id=None,
                 normalized_subject="", normalized_name=""):
        if qid is not None:
            self.id = qid
            self.subject = subject
            self.knowledge_point = text
        else:
            self.id = kp_id
            self.normalized_subject = normalized_subject
            self.normalized_name = normalized_name


def _kp(kp_id, subject, name):
    return _Row(kp_id=kp_id, normalized_subject=subject, normalized_name=name)


def _q(qid, subject, text):
    return _Row(qid=qid, subject=subject, text=text)


def test_backfill_exact_match():
    index = build_index([_kp(7, "数据结构", "栈和队列")])
    plan = plan_backfill([_q(1, "数据结构", "栈和队列")], index, set())
    assert plan.matched == 1 and plan.to_insert == [(1, 7)]
    assert plan.unmatched == 0 and plan.ambiguous == 0


def test_backfill_unmatched_reported_only():
    index = build_index([_kp(7, "数据结构", "栈和队列")])
    plan = plan_backfill(
        [_q(1, "数据结构", "栈和队列"), _q(2, "高等数学", "极限")], index, set()
    )
    assert plan.to_insert == [(1, 7)]
    assert plan.unmatched == 1
    assert ("高等数学", "极限") in plan.unmatched_keys
    assert plan.ambiguous == 0


def test_backfill_ambiguous_refused():
    # 人为构造重复 normalized 命中（现实中被 uq 约束阻止）验证拒绝路径
    index = {( "数据结构", "栈和队列"): [7, 8]}
    plan = plan_backfill([_q(1, "数据结构", "栈和队列")], index, set())
    assert plan.to_insert == []
    assert plan.ambiguous == 1
    assert ("数据结构", "栈和队列") in plan.ambiguous_keys


def test_backfill_idempotent_on_rerun():
    index = build_index([_kp(7, "数据结构", "栈和队列")])
    first = plan_backfill([_q(1, "数据结构", "栈和队列")], index, set())
    assert first.to_insert == [(1, 7)]
    second = plan_backfill([_q(1, "数据结构", "栈和队列")], index, {(1, 7)})
    assert second.to_insert == []
    assert second.already_linked == 1
    assert second.matched == 1


def test_backfill_never_creates_knowledge_points():
    """plan_backfill 只返回 (question, kp) 对；无任何创建 KnowledgePoint 的出口。"""
    index = build_index([_kp(7, "数据结构", "栈和队列")])
    plan = plan_backfill(
        [_q(1, "数据结构", "栈和队列"), _q(2, "数据结构", "不存在的知识点")],
        index, set(),
    )
    assert plan.to_insert == [(1, 7)]
    assert plan.unmatched_keys == {("数据结构", "不存在的知识点"): 1}
    # 返回类型中没有任何 KP 创建载荷
    assert all(isinstance(q, int) and isinstance(k, int) for q, k in plan.to_insert)


def test_backfill_normalization_matches_service_rules():
    """大小写与空白折叠语义与 Phase 1 Python 规则一致。"""
    index = build_index([_kp(7, "data structure", "stack and queue")])
    plan = plan_backfill([_q(1, "Data  Structure", "stack   AND queue")], index, set())
    assert plan.to_insert == [(1, 7)]


# ---------- production-shaped legacy expectation ----------


def test_production_shape_all_unmatched_when_kp_table_empty():
    """生产现状：kp=0 行、8 条 数据结构/栈和队列 → matched=0, unmatched=8。"""
    questions = [_q(i, "数据结构", "栈和队列") for i in range(1, 9)]
    plan = plan_backfill(questions, build_index([]), set())
    assert plan.matched == 0
    assert plan.unmatched == 8
    assert plan.to_insert == []
    assert plan.ambiguous == 0
