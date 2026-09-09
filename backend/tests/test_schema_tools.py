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


def test_adoption_safe_20260909(engine):
    _set_version(engine, "20260909_001")
    res = inspect_adoption(engine, Base)
    assert res.status == "SAFE TO ADOPT TO 20260909_001"


def test_adoption_20260908_reconcile_present(engine):
    _set_version(engine, "20260908_001")
    res = inspect_adoption(engine, Base)
    assert res.status == "SAFE TO ADOPT TO 20260909_001"


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
    _set_version(engine, "20260909_001")
    assert inspect_adoption(engine, Base).status == "ADOPTION BLOCKED"


def test_adoption_bad_graph_blocks(engine, monkeypatch):
    from app.core import adoption_inspector

    def invalid():
        raise ValueError("invalid graph")

    monkeypatch.setattr(adoption_inspector, "migration_chain", invalid)
    _set_version(engine, "20260909_001")
    assert inspect_adoption(engine, Base).status == "ADOPTION BLOCKED"


def test_adoption_ambiguous_profiles_blocks(engine, monkeypatch):
    from app.core import adoption_inspector

    monkeypatch.setattr(adoption_inspector, "load_profiles", lambda _: {
        "20260908_001": Base, "20260909_001": Base,
    })
    _set_version(engine, "20260909_001")
    assert inspect_adoption(engine, Base).status == "ADOPTION BLOCKED"


def test_tools_only_issue_read_statements(engine):
    from sqlalchemy import event

    _set_version(engine, "20260909_001")
    statements = []
    event.listen(engine, "before_cursor_execute", lambda c, cur, sql, p, ctx, many: statements.append(sql))
    assert check_drift(engine, Base).exit_code == 0
    assert inspect_adoption(engine, Base).status.startswith("SAFE")
    assert statements
    assert all(sql.lstrip().upper().startswith(("SELECT", "PRAGMA")) for sql in statements)
