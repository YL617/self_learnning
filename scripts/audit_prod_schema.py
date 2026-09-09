"""生产数据库只读核验脚本。

用途：在服务器后端目录运行，确认线上数据库属于 A/B/C/D 哪一种状态。
严格只读：不 CREATE/ALTER/DROP/INSERT/UPDATE/DELETE，不执行 alembic stamp/upgrade。
不输出密码、完整连接字符串、用户数据、Token、Secret。

用法（在 backend 目录下）：
    .venv\\Scripts\\python ..\\scripts\\audit_prod_schema.py
或者（依赖已安装）：
    python ../scripts/audit_prod_schema.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

from app import models  # noqa: F401  确保 Base.metadata 载入全部 ORM 表
from app.core.config import get_settings
from app.core.database import Base


def _redact_engine() -> str:
    """只返回数据库方言，不返回 URL / user / password / host。"""
    try:
        url = get_settings().DATABASE_URL
        dialect = url.split(":", 1)[0].split("+", 1)[0]
        return f"dialect={dialect}"
    except Exception:
        return "dialect=unknown"


def _col_brief(column: dict) -> str:
    return (
        f"{column['name']}:{column['type']}"
        f" nullable={column['nullable']}"
        f" default={column.get('default')}"
    )


def _orm_col_brief(column) -> str:
    default = getattr(column, "default", None)
    return (
        f"{column.name}:{column.type}"
        f" nullable={bool(column.nullable)}"
        f" default={default.arg if default is not None and hasattr(default, 'arg') else default}"
    )


def main() -> int:
    print("=== 生产数据库只读核验 ===")
    print(_redact_engine())

    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    insp = inspect(engine)

    db_tables = set(insp.get_table_names())
    orm_tables = set(Base.metadata.tables.keys())
    system_tables = {"alembic_version"}
    business_db_tables = db_tables - system_tables

    # 1) alembic_version
    print("\n=== alembic_version ===")
    if "alembic_version" not in db_tables:
        print("alembic_version 表：不存在")
        version_nums = []
    else:
        print("alembic_version 表：存在")
        try:
            from sqlalchemy import text

            with engine.connect() as conn:
                rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
                version_nums = [row[0] for row in rows]
            print(f"version_num 数量：{len(version_nums)}")
            for v in version_nums:
                print(f"  revision: {v}")
        except Exception as exc:  # noqa: BLE001
            print(f"读取 alembic_version 失败：{type(exc).__name__}")
            version_nums = []

    # 2) 表数量与 ORM 差异
    print("\n=== 表数量 ===")
    print(f"数据库业务表数量：{len(business_db_tables)}")
    print(f"ORM 模型表数量：{len(orm_tables)}")
    print(f"数据库全部表数量（含 alembic_version）：{len(db_tables)}")

    missing_tables = sorted(orm_tables - business_db_tables)
    extra_tables = sorted(business_db_tables - orm_tables)
    if missing_tables:
        print("ORM 有、线上库没有的表：")
        for t in missing_tables:
            print(f"  - {t}")
    else:
        print("ORM 有、线上库没有的表：无")
    if extra_tables:
        print("线上库有、ORM 没有的表：")
        for t in extra_tables:
            print(f"  - {t}")
    else:
        print("线上库有、ORM 没有的表：无")

    # 3) 逐表列/索引/约束差异
    print("\n=== 逐表结构对照 ===")
    diff_tables = 0
    touched_tables = sorted(orm_tables | business_db_tables)
    for table_name in touched_tables:
        db_columns: dict[str, dict] = {}
        orm_columns = {}
        try:
            if table_name in db_tables:
                for col in insp.get_columns(table_name):
                    db_columns[col["name"]] = col
        except Exception as exc:  # noqa: BLE001
            print(f"[{table_name}] 读取线上列失败：{type(exc).__name__}")
            continue
        if table_name in orm_tables:
            orm_columns = {col.name: col for col in Base.metadata.tables[table_name].columns}

        missing_cols = sorted(set(orm_columns) - set(db_columns))
        extra_cols = sorted(set(db_columns) - set(orm_columns))
        type_mismatch = []
        nullable_mismatch = []
        default_mismatch = []
        for col in db_columns:
            if col in orm_columns:
                db_t = str(db_columns[col]["type"]).lower()
                orm_t = str(orm_columns[col].type).lower()
                if db_t != orm_t:
                    type_mismatch.append((col, db_t, orm_t))
                if bool(db_columns[col]["nullable"]) != bool(orm_columns[col].nullable):
                    nullable_mismatch.append(
                        (col, db_columns[col]["nullable"], bool(orm_columns[col].nullable))
                    )
                if db_columns[col].get("default") != getattr(orm_columns[col], "default", None):
                    default_mismatch.append(col)

        db_index_nonpk = set()
        orm_index_nonpk = set()
        try:
            for idx in insp.get_indexes(table_name):
                if not idx.get("unique"):
                    db_index_nonpk.add(tuple(idx["column_names"]))
        except Exception:  # noqa: BLE001
            pass
        if table_name in orm_tables:
            for idx in Base.metadata.tables[table_name].indexes:
                if not idx.unique:
                    orm_index_nonpk.add(tuple(col.name for col in idx.columns))

        db_unique = set()
        orm_unique = set()
        try:
            for uc in insp.get_unique_constraints(table_name):
                db_unique.add(tuple(sorted(uc["column_names"])))
        except Exception:  # noqa: BLE001
            pass
        if table_name in orm_tables:
            for uc in Base.metadata.tables[table_name].constraints:
                if uc.__class__.__name__ == "UniqueConstraint":
                    orm_unique.add(tuple(sorted(col.name for col in uc.columns)))

        issues = []
        if missing_cols:
            issues.append(f"缺列: {missing_cols}")
        if extra_cols:
            issues.append(f"多列: {extra_cols}")
        if type_mismatch:
            issues.append(f"类型不一致: {type_mismatch}")
        if nullable_mismatch:
            issues.append(f"nullable不一致: {nullable_mismatch}")
        if default_mismatch and False:  # default 对比太脆弱，默认不当作硬差异
            issues.append(f"default不一致: {default_mismatch}")
        if db_index_nonpk != orm_index_nonpk:
            issues.append(f"普通索引不一致: db={sorted(db_index_nonpk)} orm={sorted(orm_index_nonpk)}")
        if db_unique != orm_unique:
            issues.append(f"unique约束不一致: db={sorted(db_unique)} orm={sorted(orm_unique)}")

        if issues:
            diff_tables += 1
            print(f"\n[{table_name}]")
            for issue in issues:
                print(f"  - {issue}")

    print(f"\n存在结构差异的表数量：{diff_tables}")

    # 4) 迁移链
    print("\n=== Alembic 迁移链（只读，不执行） ===")
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config("alembic.ini")
        script = ScriptDirectory.from_config(cfg)
        for rev in script.walk_revisions():
            first_line = (rev.doc or "").strip().splitlines()
            title = first_line[0] if first_line else rev.revision
            print(f"{rev.revision} (parent={rev.down_revision}) :: {title}")
    except Exception as exc:  # noqa: BLE001
        print(f"读取迁移链失败：{type(exc).__name__}；请确认在 backend 目录运行")

    # 5) 分类线索
    print("\n=== 分类线索 ===")
    print(f"alembic_version 存在：{'是' if version_nums else '否'}")
    print(f"version_num 数量：{len(version_nums)}")
    print(f"缺少 ORM 表数量：{len(missing_tables)}")
    print(f"结构差异表数量：{diff_tables}")
    if version_nums and not missing_tables and diff_tables == 0:
        print("倾向：A（Alembic 正常管理，revision 与 Schema 基本一致）")
    elif not version_nums and (business_db_tables or not missing_tables):
        print("倾向：B（业务表存在，但没有 alembic_version；或纯 create_all）")
    elif version_nums and (missing_tables or diff_tables):
        print("倾向：C 或 C+D（有 alembic_version，但 Schema 与 revision 不一致）")
    else:
        print("倾向：D（Schema 接近当前 ORM，但迁移历史不完整）")
    print("注意：上述倾向仅供参考，最终分类需结合真实 Schema 明细人工确认。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
