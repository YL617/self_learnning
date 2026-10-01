import pytest
from sqlalchemy import create_engine, inspect, text

from app import models  # noqa: F401
from app.core.adoption_inspector import inspect_adoption
from app.core.database import Base
from app.core.schema_drift import check_drift


def mutate_inspection(monkeypatch, engine, method, table, change):
    from app.core import schema_drift

    inspector = inspect(engine)
    original = getattr(inspector, method)

    def replaced(name, *args, **kwargs):
        result = original(name, *args, **kwargs)
        if name == table:
            change(result)
        return result

    monkeypatch.setattr(inspector, method, replaced)
    monkeypatch.setattr(schema_drift, "inspect", lambda _: inspector)


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def _set_version(engine, version: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES (:v)"), {"v": version})


def _drop_table(engine, table: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {table}"))


def _drop_column(engine, table: str, column: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))


def test_drift_full_schema_exit0(engine):
    result = check_drift(engine, Base)
    assert result.errors == []
    assert result.exit_code == 0


def test_redundant_primary_key_indexes_are_not_in_orm_metadata():
    tables = (
        "activation_codes",
        "ai_provider_snapshots",
        "course_recommendations",
        "focus_tags",
        "pet_memories",
        "pet_messages",
        "pet_play_sessions",
        "plan_chat_messages",
        "plan_chat_sessions",
    )
    for table_name in tables:
        table = Base.metadata.tables[table_name]
        assert table.c.id.primary_key is True
        assert [i for i in table.indexes if i.name == f"ix_{table_name}_id"] == []


def test_new_tables_have_no_redundant_primary_key_index():
    """通用规则：20260909_001 之后新增的表禁止 PK 冗余索引。

    PRIMARY KEY 自身已提供索引，额外 ix_<table>_id 是冗余。
    历史表沿用已冻结的 20260909_001 契约（其 ix_<table>_id 仍被 drift 要求存在），
    本阶段不做清理，故按冻结合同豁免。
    """
    from app.core.schema_profiles import load_profiles

    historical = set(load_profiles(Base)["20260909_001"].metadata.tables)
    checked = 0
    for name, table in sorted(Base.metadata.tables.items()):
        if name in historical:
            continue
        if [c.name for c in table.primary_key.columns] != ["id"]:
            continue
        checked += 1
        assert table.c.id.primary_key is True, name
        assert [i.name for i in table.indexes if i.name == f"ix_{name}_id"] == [], name
    assert checked > 0


def test_question_knowledge_points_index_and_constraint_contract():
    from sqlalchemy import UniqueConstraint

    table = Base.metadata.tables["question_knowledge_points"]
    index_names = {i.name for i in table.indexes}

    # PK 为 id，且不再有冗余的 PK 索引。
    assert [c.name for c in table.primary_key.columns] == ["id"]
    assert "ix_question_knowledge_points_id" not in index_names
    # UNIQUE 覆盖 (question_id, knowledge_point_id)，可服务 question_id 前缀查询。
    assert "ix_question_knowledge_points_question_id" not in index_names
    uniques = {tuple(c.name for c in u.columns): u.name
               for u in table.constraints if isinstance(u, UniqueConstraint)}
    assert uniques == {
        ("question_id", "knowledge_point_id"): "uq_question_knowledge_points_pair"
    }
    # 反向查询（按知识点找题）所需的独立索引保留。
    assert "ix_question_knowledge_points_knowledge_point_id" in index_names

    # FK 动作：题目删除级联清理关联；知识点删除由 RESTRICT 兜底（Service 已预检）。
    fks = {fk.parent.name: fk for fk in table.foreign_keys}
    assert fks["question_id"].target_fullname == "questions.id"
    assert fks["question_id"].ondelete == "CASCADE"
    assert fks["knowledge_point_id"].target_fullname == "knowledge_points.id"
    assert fks["knowledge_point_id"].ondelete == "RESTRICT"


def test_user_knowledge_point_mastery_contract():
    """大阶段 2：掌握度表 UNIQUE(user_id, knowledge_point_id) + 反向索引。"""
    from sqlalchemy import UniqueConstraint

    table = Base.metadata.tables["user_knowledge_point_mastery"]
    index_names = {i.name for i in table.indexes}

    assert [c.name for c in table.primary_key.columns] == ["id"]
    assert "ix_user_knowledge_point_mastery_id" not in index_names
    uniques = {tuple(c.name for c in u.columns): u.name
               for u in table.constraints if isinstance(u, UniqueConstraint)}
    assert uniques == {
        ("user_id", "knowledge_point_id"): "uq_user_knowledge_point_mastery_pair"
    }
    # UNIQUE 已覆盖 user_id 前缀，无需额外 user_id 单列索引。
    assert "ix_user_knowledge_point_mastery_user_id" not in index_names
    assert "ix_user_knowledge_point_mastery_knowledge_point_id" in index_names


def test_wrong_book_items_unique_pair_contract():
    """大阶段 2：一个用户 + 一道题只允许一条错题记录。"""
    from sqlalchemy import UniqueConstraint

    table = Base.metadata.tables["wrong_book_items"]
    uniques = {tuple(c.name for c in u.columns): u.name
               for u in table.constraints if isinstance(u, UniqueConstraint)}
    assert uniques.get(("user_id", "question_id")) == "uq_wrong_book_items_user_question"


def test_user_knowledge_point_mastery_fk_actions_contract():
    """掌握度表：用户删除级联；知识点删除由 RESTRICT 兜底（Service 已预检）。"""
    table = Base.metadata.tables["user_knowledge_point_mastery"]
    fks = {fk.parent.name: fk for fk in table.foreign_keys}
    assert fks["user_id"].target_fullname == "users.id"
    assert fks["user_id"].ondelete == "CASCADE"
    assert fks["knowledge_point_id"].target_fullname == "knowledge_points.id"
    assert fks["knowledge_point_id"].ondelete == "RESTRICT"


def test_drift_missing_table(engine):
    _drop_table(engine, "plan_adjustment_logs")
    result = check_drift(engine, Base)
    assert any("MISSING TABLE plan_adjustment_logs" in e for e in result.errors)
    assert result.exit_code == 1


def test_drift_missing_column(engine):
    _drop_column(engine, "coin_transactions", "reason")
    result = check_drift(engine, Base)
    assert any("MISSING COLUMN coin_transactions.reason" in e for e in result.errors)
    assert result.exit_code == 1


def test_drift_unique_mismatch(engine):
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX ix_users_email"))
    result = check_drift(engine, Base)
    assert any("UNIQUE MISMATCH users" in e for e in result.errors)
    assert result.exit_code == 1


def test_drift_duplicate_unique_objects(engine):
    with engine.begin() as conn:
        conn.execute(text("CREATE UNIQUE INDEX duplicate_user_email ON users(email)"))
    result = check_drift(engine, Base)
    assert any("DUPLICATE UNIQUE users" in e for e in result.errors)


def test_adoption_complete_20261001_002(engine):
    _set_version(engine, "20261001_002")
    res = inspect_adoption(engine, Base)
    assert res.status == "ADOPTION COMPLETE AT 20261001_002"
    assert res.revision == "20261001_002"
    assert any("schema_matches=20261001_002" in line for line in res.info)


def test_adoption_target_revision_with_drift_blocks(engine):
    _set_version(engine, "20261001_002")
    _drop_column(engine, "users", "hashed_password")
    res = inspect_adoption(engine, Base)
    assert res.status == "ADOPTION BLOCKED"
    assert any("MISSING COLUMN users.hashed_password" in reason for reason in res.reasons)


@pytest.mark.parametrize("revision,drift,expected,exit_code", [
    ("20260908_001", False, "SAFE TO ADOPT TO 20261001_002", 0),
    ("20260909_001", False, "SAFE TO ADOPT TO 20261001_002", 0),
    ("20261001_001", False, "SAFE TO ADOPT TO 20261001_002", 0),
    ("20261001_002", False, "ADOPTION COMPLETE AT 20261001_002", 0),
    ("20261001_002", True, "ADOPTION BLOCKED", 1),
    ("unknown", False, "ADOPTION BLOCKED", 1),
])
def test_adoption_cli_status_and_exit_code(engine, monkeypatch, capsys,
                                          revision, drift, expected, exit_code):
    import sqlalchemy

    from app.core.adoption_inspector import main

    _set_version(engine, revision)
    if drift:
        _drop_column(engine, "users", "hashed_password")
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda _: engine)
    assert main() == exit_code
    assert capsys.readouterr().out.splitlines()[0] == expected


def test_adoption_20260908_reconcile_present(engine):
    _set_version(engine, "20260908_001")
    res = inspect_adoption(engine, Base)
    assert res.status == "SAFE TO ADOPT TO 20261001_002"


def test_adoption_20260907_missing_knowledge_points(engine):
    _set_version(engine, "20260907_001")
    _drop_table(engine, "knowledge_points")
    res = inspect_adoption(engine, Base)
    # This is a partially adopted create_all shape, NOT the historical revision.
    # Running strict reconciliation here would duplicate tables: fail closed.
    assert res.status == "ADOPTION BLOCKED"


def test_adoption_unknown_revision(engine):
    _set_version(engine, "20999999_999")
    res = inspect_adoption(engine, Base)
    assert res.status == "ADOPTION BLOCKED"


def test_adoption_schema_versus_version_conflict(engine):
    _set_version(engine, "20260908_001")
    _drop_table(engine, "todos")
    res = inspect_adoption(engine, Base)
    assert res.status == "ADOPTION BLOCKED"


def test_adoption_missing_critical_column(engine):
    _set_version(engine, "20260908_001")
    _drop_column(engine, "users", "hashed_password")
    res = inspect_adoption(engine, Base)
    assert res.status == "ADOPTION BLOCKED"


def test_drift_nullable(engine, monkeypatch):
    mutate_inspection(monkeypatch, engine, "get_columns", "users",
                      lambda cols: next(c for c in cols if c["name"] == "username").update(nullable=True))
    assert any("NULLABLE users.username" in e for e in check_drift(engine, Base).errors)


@pytest.mark.parametrize("value,allowed", [("'user'", True), ("'admin'", False)])
def test_whitelisted_value_checked(engine, monkeypatch, value, allowed):
    mutate_inspection(monkeypatch, engine, "get_columns", "users",
                      lambda cols: next(c for c in cols if c["name"] == "role").update(default=value))
    result = check_drift(engine, Base)
    assert bool(result.errors) is not allowed
    assert bool(result.warnings) is allowed


def test_unlisted_default_fails(engine, monkeypatch):
    mutate_inspection(monkeypatch, engine, "get_columns", "users",
                      lambda cols: next(c for c in cols if c["name"] == "username").update(default="'x'"))
    assert any("SERVER_DEFAULT users.username" in e for e in check_drift(engine, Base).errors)


def test_both_defaults_present_but_different(engine, monkeypatch):
    mutate_inspection(monkeypatch, engine, "get_columns", "users",
                      lambda cols: next(c for c in cols if c["name"] == "created_at").update(default="'2000-01-01'"))
    assert any("SERVER_DEFAULT users.created_at" in e for e in check_drift(engine, Base).errors)


def test_fk_action_fails(engine, monkeypatch):
    mutate_inspection(monkeypatch, engine, "get_foreign_keys", "questions",
                      lambda fks: fks[0].update(options={"ondelete": "SET NULL"}))
    assert any("FK MISMATCH questions" in e for e in check_drift(engine, Base).errors)


def test_business_index_extra(engine):
    with engine.begin() as connection:
        connection.execute(text("CREATE INDEX extra_users_nickname ON users(nickname)"))
    assert any("INDEX MISMATCH users" in e for e in check_drift(engine, Base).errors)


def test_explicit_pk_column_index_required(engine):
    with engine.begin() as connection:
        connection.execute(text("DROP INDEX ix_users_id"))
    assert any("INDEX MISMATCH users" in e for e in check_drift(engine, Base).errors)


@pytest.mark.parametrize("dialect,index_name,allowed", [
    ("mysql", "fk_auto_test", True),
    ("sqlite", "fk_auto_test", False),
    ("mysql", "manual_extra", False),
])
def test_fk_index_requires_mysql_and_provenance(engine, monkeypatch, dialect, index_name, allowed):
    from app.core import schema_drift

    inspector = inspect(engine)
    original_fk, original_index = inspector.get_foreign_keys, inspector.get_indexes

    def fks(table):
        result = original_fk(table)
        if table == "activation_codes":
            result[0]["name"] = "fk_auto_test"
        return result

    def indexes(table):
        result = original_index(table)
        if table == "activation_codes":
            result.append({"name": index_name, "column_names": fks(table)[0]["constrained_columns"], "unique": False})
        return result

    monkeypatch.setattr(inspector, "get_foreign_keys", fks)
    monkeypatch.setattr(inspector, "get_indexes", indexes)
    monkeypatch.setattr(schema_drift, "inspect", lambda _: inspector)
    monkeypatch.setattr(engine.dialect, "name", dialect)
    result = check_drift(engine, Base)
    assert bool(result.errors) is not allowed
    assert bool(result.warnings) is allowed


def test_mysql_type_normalization():
    from sqlalchemy import Boolean, String
    from sqlalchemy.dialects.mysql import TINYINT

    from app.core.schema_drift import _type_family

    assert _type_family(TINYINT(display_width=1)) == _type_family(Boolean())
    assert _type_family(TINYINT(display_width=4)) != _type_family(Boolean())
    assert _type_family(String(collation="utf8mb4_unicode_ci")) == _type_family(String())


def test_adoption_index_missing_blocks(engine):
    _set_version(engine, "20260908_001")
    with engine.begin() as connection:
        connection.execute(text("DROP INDEX ix_course_recommendations_status"))
    assert inspect_adoption(engine, Base).status == "ADOPTION BLOCKED"


def test_adoption_no_revision_blocks(engine):
    assert inspect_adoption(engine, Base).status == "ADOPTION BLOCKED"


def test_adoption_multiple_revisions_blocks(engine):
    _set_version(engine, "20260908_001")
    _set_version(engine, "20261001_002")
    assert inspect_adoption(engine, Base).status == "ADOPTION BLOCKED"


def test_adoption_bad_graph_blocks(engine, monkeypatch):
    from app.core import adoption_inspector

    def invalid():
        raise ValueError("invalid graph")

    monkeypatch.setattr(adoption_inspector, "migration_chain", invalid)
    _set_version(engine, "20261001_002")
    assert inspect_adoption(engine, Base).status == "ADOPTION BLOCKED"


def test_adoption_ambiguous_profiles_blocks(engine, monkeypatch):
    from app.core import adoption_inspector

    monkeypatch.setattr(adoption_inspector, "load_profiles", lambda _: {
        "20260908_001": Base, "20260909_001": Base,
    })
    _set_version(engine, "20261001_002")
    assert inspect_adoption(engine, Base).status == "ADOPTION BLOCKED"


def test_tools_only_issue_read_statements(engine):
    from sqlalchemy import event

    _set_version(engine, "20261001_002")
    statements = []
    event.listen(engine, "before_cursor_execute", lambda c, cur, sql, p, ctx, many: statements.append(sql))
    assert check_drift(engine, Base).exit_code == 0
    assert inspect_adoption(engine, Base).status == "ADOPTION COMPLETE AT 20261001_002"
    assert statements
    assert all(sql.lstrip().upper().startswith(("SELECT", "PRAGMA")) for sql in statements)
