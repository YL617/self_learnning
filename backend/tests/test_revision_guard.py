import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, text

from app.core.database import Base
from app.core.revision_guard import (
    SchemaRevisionError,
    expected_head,
    require_schema_revision,
)
from app.core.schema_drift import DriftResult


@pytest.mark.parametrize("versions", [[], ["20260908_001"], ["unknown"],
                                      ["20260909_001", "20260908_001"]])
def test_guard_refuses_missing_old_unknown_or_multiple_revisions(versions):
    engine = create_engine("sqlite://")
    try:
        if versions:
            with engine.begin() as conn:
                conn.execute(text("CREATE TABLE alembic_version(version_num VARCHAR(32))"))
                for revision in versions:
                    conn.execute(text("INSERT INTO alembic_version VALUES (:v)"), {"v": revision})
        with pytest.raises(SchemaRevisionError):
            require_schema_revision(engine)
    finally:
        engine.dispose()


def test_guard_is_read_only_and_detects_newer_database():
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE alembic_version(version_num VARCHAR(32))"))
            conn.execute(text("INSERT INTO alembic_version VALUES (:v)"), {"v": expected_head()})
        statements = []
        event.listen(engine, "before_cursor_execute",
                     lambda c, cur, sql, p, ctx, many: statements.append(sql))
        assert require_schema_revision(engine) == "20260909_001"
        assert all(s.lstrip().upper().startswith(("SELECT", "PRAGMA")) for s in statements)
        with engine.begin() as conn:
            conn.execute(text("UPDATE alembic_version SET version_num='20990101_001'"))
        with pytest.raises(SchemaRevisionError):
            require_schema_revision(engine)
    finally:
        engine.dispose()


@pytest.mark.parametrize("migrated", [False, True])
def test_production_lifespan_never_calls_create_all(tmp_path, monkeypatch, migrated):
    url = "sqlite:///" + (tmp_path / "startup.db").as_posix()
    backend = Path(__file__).resolve().parents[1]
    if migrated:
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend,
                       env={**os.environ, "DATABASE_URL": url}, check=True, capture_output=True)
    engine = create_engine(url, connect_args={"check_same_thread": False})
    module = importlib.import_module("app.main")
    monkeypatch.setattr(module, "engine", engine)
    monkeypatch.setattr(module.settings, "APP_ENV", "prod")
    monkeypatch.setattr(module.settings, "ADMIN_INITIAL_EMAIL", "")

    def forbidden(*args, **kwargs):
        raise AssertionError("Production must never call create_all")

    monkeypatch.setattr(Base.metadata, "create_all", forbidden)
    before = set(inspect(engine).get_table_names())
    try:
        if migrated:
            with TestClient(module.app) as client:
                assert client.get("/health").status_code == 200
        else:
            with pytest.raises(SchemaRevisionError), TestClient(module.app):
                pass
        assert set(inspect(engine).get_table_names()) == before
    finally:
        engine.dispose()


@pytest.mark.parametrize("signal_name", ["worker_init", "beat_init"])
def test_background_guard_stops_process_on_schema_mismatch(monkeypatch, signal_name):
    from celery import signals

    from app.core import revision_guard
    from app.tasks import celery_app  # noqa: F401

    def fail(engine):
        raise SchemaRevisionError("startup refused")

    monkeypatch.setattr(revision_guard, "require_schema_revision", fail)
    with pytest.raises(SystemExit, match="startup refused"):
        getattr(signals, signal_name).send(sender=object())


def test_unknown_warning_is_ci_failure():
    assert DriftResult(warnings=["unapproved normalization"]).exit_code == 1
    assert DriftResult(warnings=["FK AUTO INDEX example(user_id)"]).exit_code == 0


def test_guard_redacts_connection_error():
    class Broken:
        def connect(self):
            raise RuntimeError("mysql://user:secret@host/db")

    with pytest.raises(SchemaRevisionError) as raised:
        require_schema_revision(Broken())
    assert "secret" not in str(raised.value)
