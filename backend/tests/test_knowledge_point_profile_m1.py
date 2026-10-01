"""大阶段 4 M1：知识点内容元数据 + 导入批次的契约与行为验证。

覆盖范围（对应 M1 验收项）：
  - 新字段可写入、可读回、可清空；
  - 稳定编码(code)唯一约束在服务层与 DB 层都被执行；
  - 难度词表单一来源，且被 DB CHECK 钉死；
  - 批次表默认值、状态机约束、SET NULL 关联语义；
  - **红线**：knowledge_points.difficulty 不参与掌握度计算。

迁移的 upgrade / downgrade / upgrade 往返与 drift 见
tests/test_schema_migrations.py（那里用真实 Alembic 重放）。
"""

import uuid

import pytest
from sqlalchemy import create_engine, delete, event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import Base, SessionLocal
from app.models import (
    AnswerRecord,
    KnowledgePoint,
    KnowledgePointImportBatch,
    KnowledgePointPrerequisite,
    Question,
    QuestionKnowledgePoint,
    User,
    UserKnowledgePointMastery,
    WrongBookItem,
)
from app.services.knowledge_point_service import KnowledgePointService

API = "/api/v1"

AI_SUBJECT = "Mock Subject"
CORRECT_ANSWER = "A"


def _wipe() -> None:
    """清理本模块会写入的表；顺序必须满足 FK 依赖（先删引用方）。"""
    with SessionLocal() as db:
        db.execute(delete(AnswerRecord))
        db.execute(delete(WrongBookItem))
        db.execute(delete(UserKnowledgePointMastery))
        db.execute(delete(QuestionKnowledgePoint))
        db.execute(delete(KnowledgePointPrerequisite))
        db.execute(delete(Question))
        db.execute(delete(KnowledgePoint))
        db.execute(delete(KnowledgePointImportBatch))
        db.commit()


@pytest.fixture(autouse=True)
def _clean_profile_tables():
    _wipe()
    yield
    _wipe()


# ------------------------------------------------------------------ 辅助


def _register(client, role: str = "user") -> tuple[dict, dict]:
    suffix = uuid.uuid4().hex[:10]
    response = client.post(
        f"{API}/auth/register",
        json={
            "email": f"m1_{suffix}@example.com",
            "username": f"m1_{suffix}",
            "password": "123456",
        },
    )
    assert response.status_code == 201, response.text
    auth = response.json()
    if role != "user":
        with SessionLocal() as db:
            db.get(User, auth["user"]["id"]).role = role
            db.commit()
    return auth, {"Authorization": f"Bearer {auth['access_token']}"}


def _create_kp(client, headers, **payload) -> dict:
    body = {"name": "栈", "subject": AI_SUBJECT, **payload}
    response = client.post(f"{API}/knowledge-points", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _get_kp(client, headers, kp_id: int) -> dict:
    response = client.get(f"{API}/knowledge-points/{kp_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _patch_kp(client, headers, kp_id: int, payload: dict) -> dict:
    response = client.patch(
        f"{API}/knowledge-points/{kp_id}", headers=headers, json=payload
    )
    assert response.status_code == 200, response.text
    return response.json()


def _raw(sql: str, **params) -> None:
    with SessionLocal() as db:
        db.execute(text(sql), params)
        db.commit()


# ------------------------------------------------------------------ A. 字段


def test_profile_columns_round_trip_via_api(client):
    """5 个新字段可写入并原样读回；aliases 以字符串数组暴露。"""
    admin, headers = _register(client, "admin")
    created = _create_kp(
        client,
        headers,
        code="DS.STACK",
        aliases=["堆栈", "stack"],
        difficulty="easy",
        estimated_minutes=25,
        description="后进先出",
    )
    assert created["code"] == "DS.STACK"
    assert created["aliases"] == ["堆栈", "stack"]
    assert created["difficulty"] == "easy"
    assert created["estimated_minutes"] == 25
    assert created["import_batch_id"] is None

    fetched = _get_kp(client, headers, created["id"])
    assert fetched == created
    assert admin["user"]["id"] is not None  # 管理员身份确实是创建者


def test_alias_input_is_normalized_on_write_and_read(client):
    """别名去空白、丢空项、按原顺序去重；ORM 读回的是真正的 list 而不是字符串。"""
    _, headers = _register(client, "admin")
    created = _create_kp(
        client, headers, name="队列", aliases=["  队列  ", "queue", "queue", "", "   "]
    )
    assert created["aliases"] == ["队列", "queue"]

    with SessionLocal() as db:
        row = db.get(KnowledgePoint, created["id"])
        assert row.aliases == ["队列", "queue"]
        assert isinstance(row.aliases, list)


def test_alias_list_rejects_overlong_items_and_too_many_items(client):
    _, headers = _register(client, "admin")
    too_long = client.post(
        f"{API}/knowledge-points",
        headers=headers,
        json={"name": "栈", "subject": AI_SUBJECT, "aliases": ["x" * 101]},
    )
    assert too_long.status_code == 422, too_long.text
    too_many = client.post(
        f"{API}/knowledge-points",
        headers=headers,
        json={"name": "栈", "subject": AI_SUBJECT, "aliases": [f"a{i}" for i in range(21)]},
    )
    assert too_many.status_code == 422, too_many.text


def test_unknown_difficulty_is_rejected(client):
    _, headers = _register(client, "admin")
    response = client.post(
        f"{API}/knowledge-points",
        headers=headers,
        json={"name": "栈", "subject": AI_SUBJECT, "difficulty": "简单"},
    )
    assert response.status_code == 422, response.text


def test_negative_estimated_minutes_is_rejected(client):
    _, headers = _register(client, "admin")
    response = client.post(
        f"{API}/knowledge-points",
        headers=headers,
        json={"name": "栈", "subject": AI_SUBJECT, "estimated_minutes": -1},
    )
    assert response.status_code == 422, response.text


def test_duplicate_code_is_rejected_with_409(client):
    _, headers = _register(client, "admin")
    _create_kp(client, headers, name="栈", code="DS.STACK")
    # 大小写不同也算占用：两个方言必须给出同样行为。
    conflict = client.post(
        f"{API}/knowledge-points",
        headers=headers,
        json={"name": "队列", "subject": AI_SUBJECT, "code": "ds.stack"},
    )
    assert conflict.status_code == 409, conflict.text


def test_profile_fields_can_be_cleared_and_code_reused(client):
    _, headers = _register(client, "admin")
    first = _create_kp(client, headers, name="栈", code="DS.STACK", difficulty="hard")
    cleared = _patch_kp(
        client, headers, first["id"], {"code": None, "difficulty": None, "aliases": None}
    )
    assert cleared["code"] is None
    assert cleared["difficulty"] is None
    assert cleared["aliases"] is None

    # 清空后编码可被其他知识点复用。
    second = _create_kp(client, headers, name="队列", code="DS.STACK")
    assert second["code"] == "DS.STACK"

    # 未提及的字段不受影响：description 保持原值。
    assert _get_kp(client, headers, first["id"])["description"] is None


def test_partial_update_keeps_untouched_profile_fields(client):
    _, headers = _register(client, "admin")
    created = _create_kp(
        client, headers, code="DS.STACK", aliases=["堆栈"], difficulty="hard",
        estimated_minutes=30,
    )
    updated = _patch_kp(client, headers, created["id"], {"estimated_minutes": 45})
    assert updated["estimated_minutes"] == 45
    assert updated["code"] == "DS.STACK"
    assert updated["aliases"] == ["堆栈"]
    assert updated["difficulty"] == "hard"


def test_service_rejects_unknown_difficulty_and_negative_minutes():
    """绕过 API 直连服务层时同样不许写入脏值（DB CHECK 之前的第一道闸门）。"""
    with SessionLocal() as db:
        service = KnowledgePointService(db)
        with pytest.raises(ValueError):
            service.create(name="栈", subject="S", difficulty="简单")
        with pytest.raises(ValueError):
            service.create(name="栈", subject="S", estimated_minutes=-5)
        db.rollback()


# ------------------------------------------------------------------ B. DB 约束


def test_code_unique_constraint_is_enforced_by_database():
    """服务层被绕过时，DB 唯一约束仍是最后一道防线。"""
    _raw(
        "INSERT INTO knowledge_points (name, normalized_name, subject, "
        "normalized_subject, status, source, code, created_at, updated_at) "
        "VALUES ('栈', '栈', 'S', 's', 'active', 'admin', 'DS.STACK', "
        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )
    with pytest.raises(IntegrityError):
        _raw(
            "INSERT INTO knowledge_points (name, normalized_name, subject, "
            "normalized_subject, status, source, code, created_at, updated_at) "
            "VALUES ('队列', '队列', 'S', 's', 'active', 'admin', 'DS.STACK', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )


def test_multiple_null_codes_are_allowed():
    """编码可空 —— 两库的唯一索引都允许多个 NULL，历史数据无需回填。"""
    for name in ("栈", "队列", "链表"):
        _raw(
            "INSERT INTO knowledge_points (name, normalized_name, subject, "
            "normalized_subject, status, source, created_at, updated_at) "
            f"VALUES ('{name}', '{name}', 'S', 's', 'active', 'admin', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
    with SessionLocal() as db:
        assert db.scalar(
            select(func.count(KnowledgePoint.id)).where(KnowledgePoint.code.is_(None))
        ) == 3


@pytest.mark.parametrize("column,value", [("difficulty", "'简单'"), ("estimated_minutes", "-1")])
def test_check_constraints_reject_dirty_values(column, value):
    with pytest.raises(IntegrityError):
        _raw(
            "INSERT INTO knowledge_points (name, normalized_name, subject, "
            "normalized_subject, status, source, created_at, updated_at, "
            f"{column}) VALUES ('栈', '栈', 'S', 's', 'active', 'admin', "
            f"CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, {value})"
        )


# ------------------------------------------------------------------ C. 批次表


def _new_batch(**overrides) -> int:
    with SessionLocal() as db:
        batch = KnowledgePointImportBatch(**overrides)
        db.add(batch)
        db.commit()
        return batch.id


def test_import_batch_defaults_are_safe():
    batch_id = _new_batch()
    with SessionLocal() as db:
        batch = db.get(KnowledgePointImportBatch, batch_id)
        assert batch.status == "applied"
        assert batch.conflict_strategy == "skip"
        assert batch.source_format == "tsv"
        assert batch.source_name is None
        assert batch.user_id is None
        assert batch.rolled_back_at is None
        assert [getattr(batch, name) for name in (
            "total_rows", "created_count", "updated_count",
            "skipped_count", "failed_count", "auto_parent_count",
        )] == [0, 0, 0, 0, 0, 0]


@pytest.mark.parametrize(
    "field,value",
    [("status", "'pending'"), ("conflict_strategy", "'overwrite'")],
)
def test_import_batch_state_machine_constraints(field, value):
    columns = {
        "source_format": "'tsv'",
        "conflict_strategy": "'skip'",
        "status": "'applied'",
        "total_rows": "0",
        "created_count": "0",
        "updated_count": "0",
        "skipped_count": "0",
        "failed_count": "0",
        "auto_parent_count": "0",
        "created_at": "CURRENT_TIMESTAMP",
    }
    columns[field] = value
    with pytest.raises(IntegrityError):
        _raw(
            "INSERT INTO knowledge_point_import_batches "
            f"({', '.join(columns)}) VALUES ({', '.join(columns.values())})"
        )


def _fk_enforced_engine():
    """独立引擎 + `PRAGMA foreign_keys=ON`。

    应用测试库默认不开 SQLite 外键，所以 `ondelete` 行为必须单独验证，
    否则「声明了 SET NULL」与「SET NULL 真的生效」会被混为一谈。
    """
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    return engine


def test_batch_deletion_clears_attribution_without_deleting_knowledge_point():
    """批次只是溯源信息：删批次必须清空归属，而不是连带删除知识点。"""
    engine = _fk_enforced_engine()
    try:
        with Session(bind=engine) as db:
            batch = KnowledgePointImportBatch(source_name="ds.tsv")
            db.add(batch)
            db.flush()
            kp = KnowledgePointService(db).create(
                name="栈", subject="数据结构", code="DS.STACK",
                import_batch_id=batch.id,
            )
            db.commit()
            batch_id, kp_id = batch.id, kp.id
        assert kp_id is not None

        with Session(bind=engine) as db:
            assert db.get(KnowledgePoint, kp_id).import_batch_id == batch_id
            db.delete(db.get(KnowledgePointImportBatch, batch_id))
            db.commit()

        with Session(bind=engine) as db:
            survivor = db.get(KnowledgePoint, kp_id)
            assert survivor is not None
            assert survivor.import_batch_id is None
    finally:
        engine.dispose()


def test_batch_attribution_is_cleared_when_operator_is_removed():
    """操作人被删除后导入审计必须留存，只清空归属。"""
    engine = _fk_enforced_engine()
    try:
        with Session(bind=engine) as db:
            user = User(email="operator@example.com", username="operator",
                        hashed_password="x")
            db.add(user)
            db.flush()
            batch = KnowledgePointImportBatch(user_id=user.id, source_name="ds.tsv")
            db.add(batch)
            db.commit()
            batch_id, user_id = batch.id, user.id

        with Session(bind=engine) as db:
            db.delete(db.get(User, user_id))
            db.commit()

        with Session(bind=engine) as db:
            batch = db.get(KnowledgePointImportBatch, batch_id)
            assert batch is not None
            assert batch.user_id is None
    finally:
        engine.dispose()


def test_batch_counters_reject_negative_values():
    with pytest.raises(IntegrityError):
        _raw(
            "INSERT INTO knowledge_point_import_batches (source_format, "
            "conflict_strategy, status, total_rows, created_count, updated_count, "
            "skipped_count, failed_count, auto_parent_count, created_at) "
            "VALUES ('tsv', 'skip', 'applied', 0, 0, 0, 0, 0, -1, CURRENT_TIMESTAMP)"
        )


# ------------------------------------------------------------------ D. 红线


def _answer(client, headers, question_id: int, value: str) -> dict:
    response = client.post(
        f"{API}/questions/{question_id}/answers",
        headers=headers,
        json={"user_answer": value, "spent_seconds": 10},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _generate(client, headers, kp_id: int) -> dict:
    response = client.post(
        f"{API}/questions/generate",
        headers=headers,
        json={
            "subject": AI_SUBJECT,
            "knowledge_point": "栈",
            "question_type": "choice",
            "count": 1,
            "knowledge_point_id": kp_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()[0]


def test_knowledge_point_difficulty_never_affects_mastery(client):
    """红线：knowledge_points.difficulty 只能展示，绝不能进入掌握度计算。

    做法是严格控制变量——同一个知识点、同一题型（因此 `resolve_difficulty`
    得到同样的作答侧难度）、同样的作答正确性，唯一变化的只有
    `knowledge_points.difficulty`。三者掌握度增量必须完全一致。
    """
    _, admin_headers = _register(client, "admin")
    kp = _create_kp(client, admin_headers, name="栈")

    scores: list[int] = []
    for level in (None, "hard", "easy"):
        if level is not None:
            _patch_kp(client, admin_headers, kp["id"], {"difficulty": level})
        _, headers = _register(client, "user")
        question = _generate(client, headers, kp["id"])
        _answer(client, headers, question["id"], CORRECT_ANSWER)

        response = client.get(f"{API}/mastery/{kp['id']}", headers=headers)
        assert response.status_code == 200, response.text
        row = response.json()
        # 顺便证明难度确实被写进库、也确实出现在响应里（能展示，但不参与算分）。
        assert row["knowledge_point"]["difficulty"] == level
        scores.append(row["mastery_score"])

    assert scores[0] == scores[1] == scores[2], scores
    assert scores[0] > 50


def test_difficulty_vocabulary_has_a_single_source_of_truth():
    """难度词表三方一致：服务层常量 / 掌握度权重 / 请求 Schema 枚举。"""
    from typing import get_args

    from app.schemas.knowledge import KnowledgePointDifficulty
    from app.services.knowledge_point_service import KP_DIFFICULTY_LEVELS
    from app.services.mastery import DIFFICULTY_WEIGHTS

    assert KP_DIFFICULTY_LEVELS == tuple(DIFFICULTY_WEIGHTS) == get_args(KnowledgePointDifficulty)
