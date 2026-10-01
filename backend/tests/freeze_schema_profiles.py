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
REVISIONS = ("20260907_001", "20260908_001", "20260909_001", "20261001_001",
             "20261001_002", "20261001_003")
# 已发布（生产采用过）的可信 revision：其 frozen contract 一经生成即不可变更。
# 未列入此元组的 revision 尚未发布，允许开发期重新冻结。
RELEASE_HISTORY = ("20260907_001", "20260908_001", "20260909_001", "20261001_001",
                   "20261001_002")


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


def _normalize(snapshot: dict) -> dict:
    """让快照可复现：集合型元数据（FK/UNIQUE/索引）按稳定键排序。

    Alembic batch_alter_table 重建表时，FK 的写出顺序来自
    `Table.foreign_key_constraints`（Python set），其迭代顺序随 PYTHONHASHSEED 变化。
    drift / adoption 检查本身按集合比较、与顺序无关；这里只为让 frozen contract
    在重复运行时逐字节一致。列顺序来自 CREATE TABLE 定义顺序，本身稳定，保持原样。
    """
    normalized: dict = {}
    for table, spec in snapshot.items():
        item = dict(spec)
        for key in ("fks", "unique", "indexes"):
            item[key] = sorted(
                spec[key],
                key=lambda row: json.dumps(row, sort_keys=True, ensure_ascii=False),
            )
        normalized[table] = item
    return normalized


def main():
    backend = Path(__file__).resolve().parents[1]
    path = backend / "app/core/schema_profiles.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    profiles = {k: v for k, v in existing.items() if k not in REVISIONS}
    released = set(RELEASE_HISTORY)
    with tempfile.TemporaryDirectory(prefix="schema-contracts-") as directory:
        for revision in REVISIONS:
            snapshot = snapshot_revision(backend, Path(directory), revision)
            if revision in released and revision in existing:
                if _normalize(existing[revision]) != _normalize(snapshot):
                    print(f"ERROR: frozen contract for {revision} would change; "
                          "released migrations must not be modified. Aborting.")
                    raise SystemExit(1)
                # 已发布合同逐字节保持（不做归一化重写）。
                profiles[revision] = existing[revision]
            else:
                # 尚未发布的 revision 允许开发期（重新）冻结；此处做归一化以保证可复现。
                profiles[revision] = _normalize(snapshot)

    path.write_text(json.dumps(profiles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    added = sorted(set(REVISIONS) - set(existing))
    print(f"profiles written: {sorted(profiles)}; added: {added}")


if __name__ == "__main__":
    main()
