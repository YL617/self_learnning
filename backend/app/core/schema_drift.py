"""SQLAlchemy Base.metadata vs 真实数据库结构 的归一化漂移检查。

分级：
  ERROR   = 真实 schema 漂移，导致非零退出码
  WARNING = 已知可接受差异（白名单 server_default / MySQL FK 自动索引）
  INFO    = 摘要信息
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase

from app.core.schema_reconciliation_manifest import ALLOWED_SERVER_DEFAULT_DIFFS


def _type_family(raw_type: object) -> str:
    text = str(raw_type).upper()
    base = text.split("(")[0].split()[0]
    mapping = {
        "INTEGER": "int",
        "INT": "int",
        "TINYINT": "int",
        "SMALLINT": "int",
        "BIGINT": "int",
        "VARCHAR": "varchar",
        "CHAR": "varchar",
        "TEXT": "text",
        "LONGTEXT": "text",
        "BLOB": "binary",
        "DATETIME": "datetime",
        "TIMESTAMP": "datetime",
        "DATE": "date",
        "FLOAT": "float",
        "DOUBLE": "float",
        "DECIMAL": "decimal",
        "BOOLEAN": "bool",
        "BOOL": "bool",
        "BIT": "bit",
        "JSON": "json",
    }
    if base == "TINYINT" and getattr(raw_type, "display_width", None) == 1:
        return "bool"
    return mapping.get(base, base.lower())


def normalize_default(value, column_type) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    while value.startswith("(") and value.endswith(")"):
        value = value[1:-1].strip()
    if value.upper() in {"CURRENT_TIMESTAMP", "CURRENT_TIMESTAMP()", "NOW()"}:
        return "CURRENT_TIMESTAMP"
    if len(value) >= 2 and value[0] == value[-1] == "'":
        value = value[1:-1].replace("''", "'")
    if _type_family(column_type) in {"int", "bool", "float", "decimal"}:
        value = {"true": "1", "false": "0"}.get(value.lower(), value)
        try:
            return str(Decimal(value).normalize())
        except InvalidOperation:
            pass
    return value


def python_default(column) -> str:
    if column.default is None:
        return "none"
    arg = column.default.arg
    if callable(arg):
        arg = getattr(arg, "__qualname__", getattr(arg, "__name__", "unknown"))
    return f"python: {arg}"


def _action(value):
    return (value or "NO ACTION").upper().replace("RESTRICT", "NO ACTION")


@dataclass
class DriftResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return 0 if not self.errors else 1


def _is_fk_auto_index(column_names: list[str], db_fks: list[dict]) -> bool:
    """InnoDB 为外键列自动建索引：索引列恰好等于某条 FK 的 constrained_columns。"""
    cols = tuple(sorted(column_names))
    for fk in db_fks:
        if tuple(sorted(fk["constrained_columns"])) == cols:
            return True
    return False


def _is_pk_index(column_names: list[str], pk_cols: list[str]) -> bool:
    return sorted(column_names) == sorted(pk_cols)


def check_drift(engine: Engine, base: type[DeclarativeBase]) -> DriftResult:
    insp = inspect(engine)
    result = DriftResult()
    orm_tables = set(base.metadata.tables.keys())
    db_tables = set(insp.get_table_names())
    result.info.append(f"dialect={engine.dialect.name}")
    result.info.append(f"orm_tables={len(orm_tables)} db_tables={len(db_tables & orm_tables)}")
    if "alembic_version" in db_tables:
        with engine.connect() as connection:
            versions = list(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())
        result.info.append(f"revision={versions}")
    else:
        result.info.append("revision=unversioned")

    missing_tables = sorted(orm_tables - db_tables)
    extra_business = sorted((db_tables - orm_tables) - {"alembic_version"})
    for t in missing_tables:
        result.errors.append(f"MISSING TABLE {t}")
    for t in extra_business:
        result.errors.append(f"EXTRA TABLE {t}")

    for table in sorted(orm_tables & db_tables):
        db_cols = {c["name"]: c for c in insp.get_columns(table)}
        orm_cols = {c.name: c for c in base.metadata.tables[table].columns}
        if set(db_cols) != set(orm_cols):
            for name in sorted(set(orm_cols) - set(db_cols)):
                result.errors.append(f"MISSING COLUMN {table}.{name}")
            for name in sorted(set(db_cols) - set(orm_cols)):
                result.errors.append(f"EXTRA COLUMN {table}.{name}")
        db_pk = insp.get_pk_constraint(table)["constrained_columns"]
        orm_pk = [c.name for c in base.metadata.tables[table].primary_key.columns]
        if db_pk != orm_pk:
            result.errors.append(f"PK MISMATCH {table}: db={sorted(db_pk)} orm={sorted(orm_pk)}")

        db_fks = insp.get_foreign_keys(table)
        orm_fks = {
            (tuple(f.column_keys), f.elements[0].column.table.name,
             tuple(e.column.name for e in f.elements), _action(f.ondelete), _action(f.onupdate))
            for f in base.metadata.tables[table].foreign_key_constraints
        }
        db_fk_set = {
            (tuple(f["constrained_columns"]), f["referred_table"], tuple(f["referred_columns"]),
             _action(f.get("options", {}).get("ondelete")),
             _action(f.get("options", {}).get("onupdate")))
            for f in db_fks
        }
        if db_fk_set != orm_fks:
            result.errors.append(f"FK MISMATCH {table}: db={sorted(db_fk_set)} orm={sorted(orm_fks)}")

        # unique：unique index + unique constraint（排除 FK 唯一索引噪音由 FK 比较覆盖）
        db_unique = set()
        db_unique_names: dict[tuple[str, ...], set[str]] = defaultdict(set)
        for idx in insp.get_indexes(table):
            if idx.get("unique"):
                columns = tuple(sorted(idx["column_names"]))
                db_unique.add(columns)
                db_unique_names[columns].add(idx.get("name") or "<unnamed>")
        for uc in insp.get_unique_constraints(table):
            columns = tuple(sorted(uc["column_names"]))
            db_unique.add(columns)
            db_unique_names[columns].add(uc.get("name") or "<unnamed>")
        for columns, names in db_unique_names.items():
            if len(names) > 1:
                result.errors.append(
                    f"DUPLICATE UNIQUE {table}{columns}: names={sorted(names)}"
                )
        orm_unique = set()
        for idx in base.metadata.tables[table].indexes:
            if idx.unique:
                orm_unique.add(tuple(sorted(c.name for c in idx.columns)))
        for uc in base.metadata.tables[table].constraints:
            if uc.__class__.__name__ == "UniqueConstraint":
                orm_unique.add(tuple(sorted(c.name for c in uc.columns)))
        if db_unique != orm_unique:
            result.errors.append(f"UNIQUE MISMATCH {table}: db={sorted(db_unique)} orm={sorted(orm_unique)}")

        # 业务索引：非 unique、非 PK 隐式索引；仅当 ORM 未声明的索引列恰好等于
        # 某 FK 列时，视为 InnoDB FK 自动索引并作为 WARNING，其余真实多余索引判 ERROR。
        orm_idx = set()
        for idx in base.metadata.tables[table].indexes:
            cols = tuple(c.name for c in idx.columns)
            if idx.unique:
                continue
            orm_idx.add(cols)
        db_idx = set()
        fk_col_sets = [tuple(f["constrained_columns"]) for f in db_fks]
        for idx in insp.get_indexes(table):
            cols = tuple(idx["column_names"])
            if idx.get("unique"):
                continue
            if idx.get("name") == "PRIMARY" and cols == tuple(db_pk):
                continue
            if cols in orm_idx:
                db_idx.add(cols)
            elif (engine.dialect.name == "mysql" and cols in fk_col_sets
                  and any(idx.get("name") in {f.get("name"), f["constrained_columns"][0]}
                          and cols == tuple(f["constrained_columns"]) for f in db_fks)):
                result.warnings.append(
                    f"FK AUTO INDEX {table}({','.join(idx['column_names'])})"
                )
            else:
                db_idx.add(cols)
        if db_idx != orm_idx:
            result.errors.append(f"INDEX MISMATCH {table}: db={sorted(db_idx)} orm={sorted(orm_idx)}")

        # 列级：类型族 / nullable / server_default
        for name in sorted(db_cols.keys() & orm_cols.keys()):
            db_col = db_cols[name]
            orm_col = orm_cols[name]
            if _type_family(db_col["type"]) != _type_family(orm_col.type):
                result.errors.append(
                    f"TYPE {table}.{name}: db={_type_family(db_col['type'])} orm={_type_family(orm_col.type)}"
                )
            if bool(db_col["nullable"]) != bool(orm_col.nullable):
                result.errors.append(
                    f"NULLABLE {table}.{name}: db={db_col['nullable']} orm={orm_col.nullable}"
                )
            db_def = normalize_default(db_col.get("default"), orm_col.type)
            orm_def = normalize_default(
                orm_col.server_default.arg if orm_col.server_default is not None else None,
                orm_col.type,
            )
            if db_def != orm_def:
                key = f"{table}.{name}"
                detail = ALLOWED_SERVER_DEFAULT_DIFFS.get(key, {})
                if (db_def is not None and orm_def is None and detail
                    and db_def == normalize_default(detail["migration_default"], orm_col.type)
                    and python_default(orm_col) == detail["orm_default"]):
                    result.warnings.append(
                        f"WHITELIST DEFAULT {key} ({detail.get('reason', '')})"
                    )
                else:
                    result.errors.append(f"SERVER_DEFAULT {key}: db={db_def!r} orm={orm_def!r}")
    return result


def run(engine: Engine, base: type[DeclarativeBase]) -> int:
    result = check_drift(engine, base)
    for line in result.info:
        print(f"INFO  {line}")
    for line in result.warnings:
        print(f"WARN  {line}")
    for line in result.errors:
        print(f"ERROR {line}")
    print(f"RESULT errors={len(result.errors)} warnings={len(result.warnings)}")
    return result.exit_code


def main() -> int:
    from sqlalchemy import create_engine

    from app import models  # noqa: F401
    from app.core.config import get_settings
    from app.core.database import Base

    engine = create_engine(get_settings().DATABASE_URL)
    try:
        return run(engine, Base)
    except Exception as exc:  # noqa: BLE001 -- CLI boundary must redact connection secrets.
        print(f"ERROR inspection failed ({type(exc).__name__}); details suppressed")
        return 2
    finally:
        engine.dispose()


if __name__ == "__main__":
    import sys

    sys.exit(main())
