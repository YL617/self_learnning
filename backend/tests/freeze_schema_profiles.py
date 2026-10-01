"""Replay migrations ONLY in fresh temporary SQLite files to freeze contracts.

Explicit developer utility; never accepts a URL or uses the application database.

Safety policy (Phase 2+):
  - Profiles for revisions NOT listed in REVISIONS are preserved byte-for-byte.
  - Released revisions (RELEASE_HISTORY) are replayed and compared; if their
    recomputed contract differs from the frozen one, the tool aborts instead of
    silently overwriting a trusted contract.
  - Not-yet-released revisions may be re-frozen during development.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, inspect

# 全部需要冻结/校验的 revision；新 revision 追加到元组末尾。
REVISIONS = ("20260907_001", "20260908_001", "20260909_001", "20261001_001", "20261001_002")
# 已发布（生产采用过）的可信 revision：其 frozen contract 一经生成即不可变更。
# 未列入此元组的 revision 尚未发布，允许开发期重新冻结。
RELEASE_HISTORY = ("20260907_001", "20260908_001", "20260909_001", "20261001_001")


def snapshot_revision(backend: Path, directory: Path, revision: str) -> dict:
    url = "sqlite:///" + (directory / f"{revision}.db").as_posix()
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
    engine.dispose()
    return tables


def main():
    backend = Path(__file__).resolve().parents[1]
    path = backend / "app/core/schema_profiles.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    profiles = {k: v for k, v in existing.items() if k not in REVISIONS}
    with tempfile.TemporaryDirectory(prefix="schema-contracts-") as directory:
        for revision in REVISIONS:
            profiles[revision] = snapshot_revision(backend, Path(directory), revision)

    for revision in RELEASE_HISTORY:
        if revision in existing and existing[revision] != profiles[revision]:
            print(f"ERROR: frozen contract for {revision} would change; "
                  "released migrations must not be modified. Aborting.")
            raise SystemExit(1)

    path.write_text(json.dumps(profiles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    added = sorted(set(REVISIONS) - set(existing))
    print(f"profiles written: {sorted(profiles)}; added: {added}")


if __name__ == "__main__":
    main()
