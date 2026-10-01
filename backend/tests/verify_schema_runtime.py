"""Isolated CI database replay and production-like no-op/startup verification."""

import hashlib
import json
import os

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Engine, make_url

# 可逆性验证：在真实 MySQL 上 downgrade 到这个 revision（大阶段 4 M1 引入前的
# 基线）再 upgrade 回 head。基线是常量，因此后续新增 revision 也不会让这段失效。
ROUNDTRIP_BASELINE = "20261001_003"
ROUNDTRIP_ADDED_COLUMNS = {"code", "aliases", "difficulty", "estimated_minutes", "import_batch_id"}
ROUNDTRIP_ADDED_TABLE = "knowledge_point_import_batches"


def main():
    url = os.environ["SCHEMA_TEST_DATABASE_URL"]
    parsed = make_url(url)
    if parsed.get_backend_name() != "mysql" or not (parsed.database or "").startswith("stage3_test"):
        raise RuntimeError("Use a dedicated empty MySQL database named stage3_test...")
    os.environ["DATABASE_URL"] = url
    os.environ["ADMIN_INITIAL_EMAIL"] = ""
    os.environ["APP_ENV"] = "prod"

    from alembic.config import Config
    from fastapi.testclient import TestClient

    from alembic import command
    from app.core.adoption_inspector import inspect_adoption
    from app.core.database import Base
    from app.core.revision_guard import require_schema_revision
    from app.core.schema_drift import check_drift
    from app.main import app

    engine = create_engine(url)
    try:
        assert inspect(engine).get_table_names() == [], "Test database must be genuinely empty"
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
        head = require_schema_revision(engine)
        drift = check_drift(engine, Base)
        assert drift.exit_code == 0, drift
        assert set(inspect(engine).get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
        command.check(cfg)
        print(f"FRESH MYSQL: head={head} errors=0 warnings={len(drift.warnings)} unknown=0")

        # 真实 MySQL 上的可逆性：SQLite 的 DROP COLUMN / DROP CHECK 行为与 MySQL
        # 不同，所以往返验证必须跑在 MySQL 上，不能只靠 SQLite 重放。
        command.downgrade(cfg, ROUNDTRIP_BASELINE)
        rolled_back = inspect(engine)
        assert ROUNDTRIP_ADDED_TABLE not in rolled_back.get_table_names()
        assert not (
            ROUNDTRIP_ADDED_COLUMNS
            & {c["name"] for c in rolled_back.get_columns("knowledge_points")}
        )
        command.upgrade(cfg, "head")
        assert ROUNDTRIP_ADDED_TABLE in inspect(engine).get_table_names()
        assert ROUNDTRIP_ADDED_COLUMNS <= {
            c["name"] for c in inspect(engine).get_columns("knowledge_points")
        }
        roundtrip = check_drift(engine, Base)
        assert roundtrip.exit_code == 0, roundtrip
        print(f"MYSQL ROUNDTRIP: {ROUNDTRIP_BASELINE} -> head reversible, drift errors=0")

        def fingerprint():
            reader = inspect(engine)
            schema = {
                t: [reader.get_columns(t), reader.get_pk_constraint(t), reader.get_foreign_keys(t),
                    reader.get_indexes(t), reader.get_unique_constraints(t)]
                for t in sorted(reader.get_table_names())
            }
            return hashlib.sha256(json.dumps(schema, sort_keys=True, default=str).encode()).hexdigest()

        def forbid_create_all(*args, **kwargs):
            raise AssertionError("create_all forbidden during startup")

        def reject_writes(conn, cursor, statement, params, context, many):
            assert statement.lstrip().split()[0].upper() in {"SELECT", "SHOW", "DESCRIBE", "SET"}, (
                "Unexpected write or DDL in production-like verification"
            )

        before = fingerprint()
        original = Base.metadata.create_all
        Base.metadata.create_all = forbid_create_all
        event.listen(Engine, "before_cursor_execute", reject_writes)
        try:
            command.upgrade(cfg, "head")
            with TestClient(app) as client:
                assert client.get("/health").status_code == 200
            assert inspect_adoption(engine, Base).status == f"ADOPTION COMPLETE AT {head}"
            after = fingerprint()
            assert before == after
        finally:
            Base.metadata.create_all = original
            event.remove(Engine, "before_cursor_execute", reject_writes)
        print(f"PRODUCTION-LIKE: no-op, health=200, create_all=0, DDL=0, fingerprint={after}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
