"""Real Alembic replay tests. No create_all/stamp and no application DB access."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine

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
        for revision in ("20260907_001", "20260908_001", "head"):
            subprocess.run([sys.executable, "-m", "alembic", "upgrade", revision],
                           cwd=backend, env=environment, check=True, capture_output=True)
            adoption = inspect_adoption(engine, Base)
            if revision != "head":
                assert adoption.status == f"UPGRADE REQUIRED FROM {revision}", adoption
            else:
                result = check_drift(engine, Base)
                assert result.exit_code == 0
                assert result.errors == []
                assert len(result.warnings) == 40
                assert adoption.status == "SAFE TO ADOPT TO 20260909_001"
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
    assert len(chain) == len(set(chain)) == 16
    assert chain[-1] == manifest["revision"]
