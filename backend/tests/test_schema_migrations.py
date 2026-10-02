"""Real Alembic replay tests. No create_all/stamp and no application DB access."""

import json
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

from app import models  # noqa: F401
from app.core.adoption_inspector import inspect_adoption, migration_chain
from app.core.database import Base
from app.core.schema_drift import check_drift
from app.core.schema_reconciliation_manifest import (
    RECONCILED_COLUMNS,
    RECONCILED_TABLES,
    reconciliation_manifest,
)


def test_real_empty_sqlite_upgrade_and_zero_drift(tmp_path):
    url = "sqlite:///" + (tmp_path / "fresh.db").as_posix()
    backend = Path(__file__).resolve().parents[1]
    environment = {**os.environ, "DATABASE_URL": url}
    engine = create_engine(url)
    try:
        for revision in ("20260907_001", "20260908_001", "20260909_001",
                         "20261001_001", "20261001_002", "20261001_003", "head"):
            subprocess.run([sys.executable, "-m", "alembic", "upgrade", revision],
                           cwd=backend, env=environment, check=True, capture_output=True)
            adoption = inspect_adoption(engine, Base)
            if revision != "head":
                assert adoption.status == f"UPGRADE REQUIRED FROM {revision}", adoption
            else:
                result = check_drift(engine, Base)
                assert result.exit_code == 0
                assert result.errors == []
                assert result.unknown_warnings == []
                assert adoption.status == "ADOPTION COMPLETE AT 20261002_005"
    finally:
        engine.dispose()


def test_real_sqlite_downgrade_upgrade_roundtrip(tmp_path):
    """P0：node_type 列的 downgrade 必须真正回退，再 upgrade 回到零漂移。

    分两层验证：
      1) 005 层：node_type 列 + 索引 + CHECK 加/删；
      2) 004 层：批次表与 5 个内容列的整体回退（沿用 M1 的往返契约）。
    只在隔离的临时 SQLite 上重放真实 Alembic；不触碰应用库。
    """
    url = "sqlite:///" + (tmp_path / "roundtrip.db").as_posix()
    backend = Path(__file__).resolve().parents[1]
    environment = {**os.environ, "DATABASE_URL": url}
    engine = create_engine(url)
    added_columns = {"code", "aliases", "difficulty", "estimated_minutes", "import_batch_id"}
    try:
        def alembic(*args):
            subprocess.run([sys.executable, "-m", "alembic", *args],
                           cwd=backend, env=environment, check=True, capture_output=True)

        def kp_columns() -> set[str]:
            return {c["name"] for c in inspect(engine).get_columns("knowledge_points")}

        # ---- 1) 005 层：node_type ----
        alembic("upgrade", "head")
        assert "node_type" in kp_columns()
        alembic("downgrade", "20261001_004")
        assert "node_type" not in kp_columns()
        assert inspect_adoption(engine, Base).status == "UPGRADE REQUIRED FROM 20261001_004"
        alembic("upgrade", "head")
        assert "node_type" in kp_columns()

        # ---- 2) 004 层：批次表 + 内容列 ----
        alembic("upgrade", "20261001_004")
        assert "knowledge_point_import_batches" in inspect(engine).get_table_names()
        assert added_columns <= kp_columns()

        alembic("downgrade", "20261001_003")
        assert "knowledge_point_import_batches" not in inspect(engine).get_table_names()
        columns = kp_columns()
        assert not (added_columns & columns)
        # 回退后必须是精确可信的 20261001_003：adoption 只有在「唯一可信匹配恰好
        # 等于 003」时才会给出这个结论（此时 drift 相对 head-ORM 本就应报缺失）。
        assert inspect_adoption(engine, Base).status == "UPGRADE REQUIRED FROM 20261001_003"

        alembic("upgrade", "head")
        assert "knowledge_point_import_batches" in inspect(engine).get_table_names()
        assert added_columns <= kp_columns()
        assert "node_type" in kp_columns()
        result = check_drift(engine, Base)
        assert result.errors == []
        assert result.unknown_warnings == []
        assert inspect_adoption(engine, Base).status == "ADOPTION COMPLETE AT 20261002_005"
    finally:
        engine.dispose()


def test_manifest_delta_and_historical_ownership():
    manifest = reconciliation_manifest()
    before = manifest["historical_managed_objects"]
    assert set(manifest["created_tables"]) == set(RECONCILED_TABLES)
    assert not set(before) & set(RECONCILED_TABLES)
    for table, columns in manifest["added_columns"].items():
        assert {c["name"] for c in columns} == set(RECONCILED_COLUMNS[table])
        assert not {c["name"] for c in columns} & {c["name"] for c in before[table]["columns"]}
    assert manifest["added_indexes"]["course_recommendations"][0]["name"] == "ix_course_recommendations_status"
    chain = migration_chain()
    assert len(chain) == len(set(chain)) == 21
    assert manifest["revision"] in chain
    assert chain[-1] == "20261002_005"


def test_phase2_profile_added_without_overwriting_history():
    """Phase 2 安全项：新 revision 有自己的 profile；20260909_001 合同不含新表。"""
    from app.core.schema_profiles import PROFILE_PATH

    profiles = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    assert "question_knowledge_points" in profiles["20261001_001"]
    assert "question_knowledge_points" not in profiles["20260909_001"]
    # 历史合同表数量不变（Stage 3 验收时为 32 表）
    assert len(profiles["20260909_001"]) == 32


def test_learning_state_loop_profile_added_without_overwriting_history():
    """大阶段 2：mastery 表只出现在自己的 revision；历史合同逐字节不变。"""
    from app.core.schema_profiles import PROFILE_PATH
    from app.core.schema_reconciliation_manifest import POST_RECONCILIATION_TABLES

    profiles = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    assert "user_knowledge_point_mastery" in profiles["20261001_002"]
    assert "user_knowledge_point_mastery" not in profiles["20261001_001"]
    assert POST_RECONCILIATION_TABLES["20261001_002"] == ["user_knowledge_point_mastery"]
    # wrong_book_items 唯一约束在同一 revision 内补齐
    uniques = {u["name"] for u in profiles["20261001_002"]["wrong_book_items"]["unique"]}
    assert "uq_wrong_book_items_user_question" in uniques
    assert not {u["name"] for u in profiles["20261001_001"]["wrong_book_items"]["unique"]}
    # 历史合同表数量不变
    assert len(profiles["20261001_001"]) == 33


def test_prerequisite_profile_added_without_overwriting_history():
    """大阶段 3：前置边表只出现在自己的 revision；历史合同逐字节不变。"""
    from app.core.schema_profiles import PROFILE_PATH
    from app.core.schema_reconciliation_manifest import POST_RECONCILIATION_TABLES

    profiles = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    assert "knowledge_point_prerequisites" in profiles["20261001_003"]
    assert "knowledge_point_prerequisites" not in profiles["20261001_002"]
    assert POST_RECONCILIATION_TABLES["20261001_003"] == ["knowledge_point_prerequisites"]
    table = profiles["20261001_003"]["knowledge_point_prerequisites"]
    assert {u["name"] for u in table["unique"]} == {"uq_knowledge_point_prerequisites_pair"}
    assert {i["name"] for i in table["indexes"]} == {
        "ix_knowledge_point_prerequisites_prerequisite_id"
    }
    assert len(table["fks"]) == 2
    # 上一版合同表数量不变（33 + mastery 表 = 34）
    assert len(profiles["20261001_002"]) == 34
    assert len(profiles["20260909_001"]) == 32


def test_knowledge_point_profile_added_without_overwriting_history():
    """大阶段 4 M1：批次表只出现在自己的 revision；knowledge_points 只加列。"""
    from app.core.schema_profiles import PROFILE_PATH
    from app.core.schema_reconciliation_manifest import POST_RECONCILIATION_TABLES

    profiles = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    assert "knowledge_point_import_batches" in profiles["20261001_004"]
    assert "knowledge_point_import_batches" not in profiles["20261001_003"]
    assert POST_RECONCILIATION_TABLES["20261001_004"] == ["knowledge_point_import_batches"]

    added = ("code", "aliases", "difficulty", "estimated_minutes", "import_batch_id")
    new_columns = [c["name"] for c in profiles["20261001_004"]["knowledge_points"]["columns"]]
    old_columns = [c["name"] for c in profiles["20261001_003"]["knowledge_points"]["columns"]]
    assert set(new_columns) - set(old_columns) == set(added)
    # 只追加、不重排：历史列的顺序逐位保持。
    assert new_columns[: len(old_columns)] == old_columns

    new_table = profiles["20261001_004"]["knowledge_points"]
    assert {u["name"] for u in new_table["unique"]} == {
        "uq_knowledge_points_normalized_subject_name",
        "uq_knowledge_points_code",
    }
    assert {i["name"] for i in new_table["indexes"]} == {
        "ix_knowledge_points_id",
        "ix_knowledge_points_parent_id",
        "ix_knowledge_points_import_batch_id",
    }
    assert not {u["name"] for u in profiles["20261001_003"]["knowledge_points"]["unique"]
                } - {"uq_knowledge_points_normalized_subject_name"}

    batch = profiles["20261001_004"]["knowledge_point_import_batches"]
    assert {i["name"] for i in batch["indexes"]} == {
        "ix_knowledge_point_import_batches_user_id"
    }
    assert len(batch["fks"]) == 1
    # 上一版合同表数量不变（35 + 批次表 = 36）
    assert len(profiles["20261001_003"]) == 35


def test_node_type_added_without_overwriting_history():
    """大阶段 4 P0：node_type 只出现在 005；历史合同（004 及之前）逐字节不变。"""
    from app.core.schema_profiles import PROFILE_PATH

    profiles = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    assert "20261002_005" in profiles

    new_columns = [c["name"] for c in profiles["20261002_005"]["knowledge_points"]["columns"]]
    old_columns = [c["name"] for c in profiles["20261001_004"]["knowledge_points"]["columns"]]
    # 只追加 node_type 一列，且不重排历史列。
    assert set(new_columns) - set(old_columns) == {"node_type"}
    assert new_columns[: len(old_columns)] == old_columns

    column = next(
        c for c in profiles["20261002_005"]["knowledge_points"]["columns"]
        if c["name"] == "node_type"
    )
    assert column["nullable"] is False
    assert column["type"] == "VARCHAR(16)"
    assert column["default"] == "'concept'"

    assert {i["name"] for i in profiles["20261002_005"]["knowledge_points"]["indexes"]} == {
        "ix_knowledge_points_id",
        "ix_knowledge_points_parent_id",
        "ix_knowledge_points_import_batch_id",
        "ix_knowledge_points_node_type",
    }
    # 004 合同不得出现 node_type（历史合同不可覆盖）。
    assert "node_type" not in old_columns
    # 表数量不变（只加列，不建表）。
    assert len(profiles["20261001_004"]) == 36
