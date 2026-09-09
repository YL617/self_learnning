"""Frozen migration schema contracts; loading them never opens a database."""

import json
from pathlib import Path
from types import SimpleNamespace

import sqlalchemy as sa

from app.core.schema_reconciliation_manifest import ALLOWED_SERVER_DEFAULT_DIFFS

PROFILE_PATH = Path(__file__).with_name("schema_profiles.json")


def load_profiles(base):
    specs = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    profiles = {}
    for revision, tables in specs.items():
        metadata = sa.MetaData()
        for name, spec in tables.items():
            columns = []
            for col in spec["columns"]:
                kind = col["type"].split("(")[0].upper()
                types = {"INTEGER": sa.Integer, "BOOLEAN": sa.Boolean, "VARCHAR": sa.String,
                         "TEXT": sa.Text, "DATETIME": sa.DateTime, "DATE": sa.Date,
                         "FLOAT": sa.Float, "NUMERIC": sa.Numeric}
                if kind not in types:
                    raise ValueError("Unsupported frozen type")
                sql_type = types[kind]()
                if kind == "VARCHAR":
                    sql_type = sa.String(int(col["type"].split("(")[1].rstrip(")")))
                default = col["default"]
                python_side = None
                key = f"{name}.{col['name']}"
                if key in ALLOWED_SERVER_DEFAULT_DIFFS:
                    from app.core.schema_drift import normalize_default, python_default

                    orm_col = base.metadata.tables[name].c[col["name"]]
                    allowed = ALLOWED_SERVER_DEFAULT_DIFFS[key]
                    if (normalize_default(default, sql_type)
                            != normalize_default(allowed["migration_default"], sql_type)
                            or python_default(orm_col) != allowed["orm_default"]):
                        raise ValueError("Frozen default contract mismatch")
                    default = None
                    python_side = orm_col.default
                columns.append(sa.Column(col["name"], sql_type, nullable=col["nullable"],
                                         server_default=sa.text(default) if default is not None else None,
                                         default=python_side))
            table = sa.Table(name, metadata, *columns, sa.PrimaryKeyConstraint(*spec["pk"]))
            for fk in spec["fks"]:
                table.append_constraint(sa.ForeignKeyConstraint(
                    fk["constrained_columns"],
                    [f"{fk['referred_table']}.{c}" for c in fk["referred_columns"]],
                    **{k: v for k, v in fk.get("options", {}).items()
                       if k in {"ondelete", "onupdate"}},
                ))
            for unique in spec["unique"]:
                table.append_constraint(sa.UniqueConstraint(*unique["column_names"]))
            for index in spec["indexes"]:
                sa.Index(index["name"], *(table.c[c] for c in index["column_names"]),
                         unique=bool(index["unique"]))
        profiles[revision] = SimpleNamespace(metadata=metadata)
    return profiles
