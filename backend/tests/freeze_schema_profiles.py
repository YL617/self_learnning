"""Replay migrations ONLY in fresh temporary SQLite files to freeze contracts.

Explicit developer utility; never accepts a URL or uses the application database.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, inspect


def main():
    backend = Path(__file__).resolve().parents[1]
    profiles = {}
    with tempfile.TemporaryDirectory(prefix="schema-contracts-") as directory:
        for revision in ("20260907_001", "20260908_001", "20260909_001"):
            url = "sqlite:///" + (Path(directory) / f"{revision}.db").as_posix()
            subprocess.run([sys.executable, "-m", "alembic", "upgrade", revision],
                           cwd=backend, env={**os.environ, "DATABASE_URL": url}, check=True)
            engine = create_engine(url)
            inspector = inspect(engine)
            tables = {}
            for table in inspector.get_table_names():
                if table == "alembic_version":
                    continue
                tables[table] = {
                    "columns": [{"name": c["name"], "type": str(c["type"]),
                                 "nullable": c["nullable"], "default": c["default"]}
                                for c in inspector.get_columns(table)],
                    "pk": inspector.get_pk_constraint(table)["constrained_columns"],
                    "fks": inspector.get_foreign_keys(table),
                    "unique": inspector.get_unique_constraints(table),
                    "indexes": inspector.get_indexes(table),
                }
            profiles[revision] = tables
            engine.dispose()
    path = backend / "app/core/schema_profiles.json"
    path.write_text(json.dumps(profiles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
