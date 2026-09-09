"""Fail-closed cleanup logic for the reviewed 20260908 legacy MySQL schema.

The module can inspect and execute the seven reviewed index operations. It cannot
stamp Alembic, change revisions, discover arbitrary repairs, or accept arbitrary
DDL from callers.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import inspect, text

from app.core.adoption_inspector import inspect_adoption
from app.core.legacy_cleanup_manifest import (
    LEGACY_CLEANUP_OPERATIONS,
    LEGACY_INDEX_NAMES,
    LEGACY_REVISION,
    TARGET_REVISION,
    TARGET_TABLES,
    LegacyCleanupOperation,
)
from app.core.schema_drift import check_drift

LONG_TRANSACTION_SECONDS = 60
ACTIVE_DDL_SECONDS = 5
DDL_LOCK_WAIT_SECONDS = 30
MAX_BACKUP_AGE = timedelta(hours=24)
ADOPTION_MISMATCH_REASON = "Expected one trusted schema match; got []"

RUNTIME_SOURCE_SUFFIXES = frozenset({".py", ".sql", ".sh", ".js", ".ts", ".tsx", ".vue"})
INDEX_HINT_PATTERN = re.compile(r"\b(?:USE|FORCE|IGNORE)\s+INDEX\b", re.IGNORECASE)


@dataclass(frozen=True)
class IndexSnapshot:
    name: str
    columns: tuple[str, ...]
    unique: bool
    index_type: str
    visible: bool
    sub_parts: tuple[int | None, ...]


@dataclass(frozen=True)
class CleanupSnapshot:
    dialect: str
    revision_rows: tuple[str, ...]
    tables: frozenset[str]
    table_engines: dict[str, str]
    indexes: dict[str, dict[str, IndexSnapshot]]
    primary_keys: dict[str, tuple[str, ...]]
    constrained_fk_columns: dict[str, tuple[tuple[str, ...], ...]]
    constraint_names: frozenset[tuple[str, str]]
    drift_errors: tuple[str, ...]
    adoption_status: str
    adoption_reasons: tuple[str, ...]
    busy_reasons: tuple[str, ...] = ()


@dataclass
class CleanupAssessment:
    status: str
    pending: list[LegacyCleanupOperation] = field(default_factory=list)
    already_clean: list[LegacyCleanupOperation] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    plan_fingerprint: str = ""

    @property
    def exit_code(self) -> int:
        return 0 if not self.blockers else 1


@dataclass
class CleanupApplyResult:
    status: str
    completed: list[str] = field(default_factory=list)
    executed_sql: list[str] = field(default_factory=list)
    recovery_sql: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    failure: str = ""

    @property
    def exit_code(self) -> int:
        return 0 if self.status in {"LEGACY CLEANUP COMPLETE", "ALREADY CLEAN"} else 1


def _is_exact_index(index: IndexSnapshot, operation: LegacyCleanupOperation) -> bool:
    return (
        index.name == operation.index
        and index.columns == operation.columns
        and index.unique is operation.unique
        and index.index_type.upper() == "BTREE"
        and index.visible
        and index.sub_parts == tuple(None for _ in operation.columns)
    )


def _plan_fingerprint(pending: list[LegacyCleanupOperation]) -> str:
    canonical = {
        "legacy_revision": LEGACY_REVISION,
        "target_revision": TARGET_REVISION,
        "operations": [
            {
                "operation": operation.operation,
                "table": operation.table,
                "index": operation.index,
                "columns": operation.columns,
                "unique": operation.unique,
                "forward_sql": operation.forward_sql,
            }
            for operation in pending
        ],
    }
    payload = json.dumps(canonical, ensure_ascii=True, sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def assess_snapshot(snapshot: CleanupSnapshot) -> CleanupAssessment:
    """Classify a collected state without making database calls."""
    blockers: list[str] = []
    pending: list[LegacyCleanupOperation] = []
    already_clean: list[LegacyCleanupOperation] = []

    if snapshot.dialect != "mysql":
        blockers.append("dialect must be mysql")
    if snapshot.revision_rows != (LEGACY_REVISION,):
        blockers.append(f"revision must be exactly {LEGACY_REVISION}")
    missing_tables = sorted(TARGET_TABLES - snapshot.tables)
    if missing_tables:
        blockers.append(f"missing target tables: {', '.join(missing_tables)}")
    for table in sorted(TARGET_TABLES & snapshot.tables):
        if snapshot.table_engines.get(table, "").upper() != "INNODB":
            blockers.append(f"{table} engine must be InnoDB")

    for operation in LEGACY_CLEANUP_OPERATIONS:
        table_indexes = snapshot.indexes.get(operation.table, {})
        actual = table_indexes.get(operation.index)
        if operation.operation == "drop":
            if snapshot.primary_keys.get(operation.table) != ("id",):
                blockers.append(f"{operation.table} must retain PRIMARY(id)")
            if (operation.table, operation.index) in snapshot.constraint_names:
                blockers.append(f"{operation.table}.{operation.index} backs a constraint")
            if any(
                columns[: len(operation.columns)] == operation.columns
                for columns in snapshot.constrained_fk_columns.get(operation.table, ())
            ):
                blockers.append(f"{operation.table}.{operation.index} may back a foreign key")
            if actual is None:
                already_clean.append(operation)
            elif _is_exact_index(actual, operation):
                pending.append(operation)
            else:
                blockers.append(f"{operation.table}.{operation.index} definition mismatch")
        else:
            equivalent = [
                index
                for index in table_indexes.values()
                if index.columns == operation.columns and index.name != operation.index
            ]
            if actual is None and not equivalent:
                pending.append(operation)
            elif actual is not None and _is_exact_index(actual, operation) and not equivalent:
                already_clean.append(operation)
            elif equivalent:
                blockers.append(f"{operation.table} has an equivalent differently named status index")
            else:
                blockers.append(f"{operation.table}.{operation.index} definition mismatch")

    expected_errors = [operation.expected_drift_error for operation in pending]
    if Counter(snapshot.drift_errors) != Counter(expected_errors):
        blockers.append("schema drift is not exactly the pending reviewed cleanup set")

    if pending:
        expected_reasons = [ADOPTION_MISMATCH_REASON, *expected_errors]
        if (
            snapshot.adoption_status != "ADOPTION BLOCKED"
            or Counter(snapshot.adoption_reasons) != Counter(expected_reasons)
        ):
            blockers.append("adoption blockers are not exactly the pending cleanup set")
    elif (
        snapshot.adoption_status != f"SAFE TO ADOPT TO {TARGET_REVISION}"
        or snapshot.adoption_reasons
    ):
        blockers.append("clean schema is not approved by the adoption inspector")

    if snapshot.busy_reasons:
        blockers.extend(f"CLEANUP BLOCKED: DATABASE BUSY ({reason})" for reason in snapshot.busy_reasons)

    if blockers:
        return CleanupAssessment(
            status="CLEANUP BLOCKED",
            pending=pending,
            already_clean=already_clean,
            blockers=blockers,
            plan_fingerprint=_plan_fingerprint(pending),
        )
    return CleanupAssessment(
        status="ALREADY CLEAN" if not pending else "LEGACY CLEANUP REQUIRED",
        pending=pending,
        already_clean=already_clean,
        plan_fingerprint=_plan_fingerprint(pending),
    )


def _mysql_index_snapshots(engine) -> dict[str, dict[str, IndexSnapshot]]:
    table_sql = ",".join(f"'{table}'" for table in sorted(TARGET_TABLES))
    query = text(
        "SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, INDEX_TYPE, IS_VISIBLE, "
        "SEQ_IN_INDEX, COLUMN_NAME, SUB_PART, EXPRESSION "
        "FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() "
        f"AND TABLE_NAME IN ({table_sql}) "
        "ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX"
    )
    grouped: dict[tuple[str, str], list[dict]] = {}
    with engine.connect() as connection:
        for row in connection.execute(query).mappings():
            grouped.setdefault((row["TABLE_NAME"], row["INDEX_NAME"]), []).append(dict(row))
    result: dict[str, dict[str, IndexSnapshot]] = {table: {} for table in TARGET_TABLES}
    for (table, name), rows in grouped.items():
        result[table][name] = IndexSnapshot(
            name=name,
            columns=tuple(row["COLUMN_NAME"] or "<expression>" for row in rows),
            unique=not bool(rows[0]["NON_UNIQUE"]),
            index_type=str(rows[0]["INDEX_TYPE"]),
            visible=str(rows[0]["IS_VISIBLE"]).upper() == "YES",
            sub_parts=tuple(row["SUB_PART"] for row in rows),
        )
    return result


def _generic_index_snapshots(inspector) -> dict[str, dict[str, IndexSnapshot]]:
    result: dict[str, dict[str, IndexSnapshot]] = {table: {} for table in TARGET_TABLES}
    for table in TARGET_TABLES:
        if table not in inspector.get_table_names():
            continue
        for index in inspector.get_indexes(table):
            name = index.get("name") or "<unnamed>"
            columns = tuple(index.get("column_names") or ())
            result[table][name] = IndexSnapshot(
                name=name,
                columns=columns,
                unique=bool(index.get("unique")),
                index_type="BTREE",
                visible=True,
                sub_parts=tuple(None for _ in columns),
            )
    return result


def inspect_database_busy(engine) -> tuple[str, ...]:
    """Read MySQL operational metadata; inability to inspect is itself unsafe."""
    if engine.dialect.name != "mysql":
        return ("busy inspection requires mysql",)
    table_sql = ",".join(f"'{table}'" for table in sorted(TARGET_TABLES))
    try:
        with engine.connect() as connection:
            long_transactions = connection.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.INNODB_TRX "
                    "WHERE TIMESTAMPDIFF(SECOND, trx_started, NOW()) >= :threshold"
                ),
                {"threshold": LONG_TRANSACTION_SECONDS},
            ).scalar_one()
            pending_metadata = connection.execute(
                text(
                    "SELECT COUNT(*) FROM performance_schema.metadata_locks "
                    "WHERE OBJECT_SCHEMA = DATABASE() "
                    f"AND OBJECT_NAME IN ({table_sql}) AND LOCK_STATUS = 'PENDING'"
                )
            ).scalar_one()
            active_ddl = connection.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.PROCESSLIST "
                    "WHERE TIME >= :threshold AND COMMAND <> 'Sleep' "
                    "AND (LOWER(COALESCE(INFO, '')) LIKE 'alter table%' "
                    "OR LOWER(COALESCE(INFO, '')) LIKE 'create index%' "
                    "OR LOWER(COALESCE(INFO, '')) LIKE 'drop index%') "
                    f"AND ({' OR '.join(f'LOWER(INFO) LIKE \'%{table.lower()}%\'' for table in sorted(TARGET_TABLES))})"
                ),
                {"threshold": ACTIVE_DDL_SECONDS},
            ).scalar_one()
    except Exception as exc:  # noqa: BLE001 -- fail closed without leaking SQL or credentials.
        return (f"busy inspection unavailable ({type(exc).__name__})",)
    reasons = []
    if long_transactions:
        reasons.append(f"long transactions={long_transactions}")
    if pending_metadata:
        reasons.append(f"pending metadata locks={pending_metadata}")
    if active_ddl:
        reasons.append(f"active target DDL={active_ddl}")
    return tuple(reasons)


def collect_cleanup_snapshot(engine, base, *, check_busy: bool) -> CleanupSnapshot:
    inspector = inspect(engine)
    tables = frozenset(inspector.get_table_names())
    revision_rows: tuple[str, ...] = ()
    if "alembic_version" in tables:
        with engine.connect() as connection:
            revision_rows = tuple(
                connection.execute(text("SELECT version_num FROM alembic_version")).scalars()
            )

    table_engines: dict[str, str] = {}
    if engine.dialect.name == "mysql":
        table_sql = ",".join(f"'{table}'" for table in sorted(TARGET_TABLES))
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = DATABASE() "
                    f"AND TABLE_NAME IN ({table_sql})"
                )
            ).all()
        table_engines = {table: storage_engine for table, storage_engine in rows}
        indexes = _mysql_index_snapshots(engine)
    else:
        indexes = _generic_index_snapshots(inspector)

    primary_keys = {}
    constrained_fk_columns = {}
    constraint_names = set()
    for table in TARGET_TABLES & tables:
        pk = inspector.get_pk_constraint(table)
        primary_keys[table] = tuple(pk.get("constrained_columns") or ())
        if pk.get("name"):
            constraint_names.add((table, pk["name"]))
        fks = inspector.get_foreign_keys(table)
        constrained_fk_columns[table] = tuple(
            tuple(fk.get("constrained_columns") or ()) for fk in fks
        )
        for fk in fks:
            if fk.get("name"):
                constraint_names.add((table, fk["name"]))
        for unique in inspector.get_unique_constraints(table):
            if unique.get("name"):
                constraint_names.add((table, unique["name"]))

    drift = check_drift(engine, base)
    adoption = inspect_adoption(engine, base)
    return CleanupSnapshot(
        dialect=engine.dialect.name,
        revision_rows=revision_rows,
        tables=tables,
        table_engines=table_engines,
        indexes=indexes,
        primary_keys=primary_keys,
        constrained_fk_columns=constrained_fk_columns,
        constraint_names=frozenset(constraint_names),
        drift_errors=tuple(drift.errors),
        adoption_status=adoption.status,
        adoption_reasons=tuple(adoption.reasons),
        busy_reasons=inspect_database_busy(engine) if check_busy else (),
    )


def scan_repository_index_dependencies(repo_root: Path | None = None) -> list[str]:
    """Scan runtime source only; external BI/manual SQL remains unknowable."""
    root = repo_root or Path(__file__).resolve().parents[3]
    source_roots = (root / "backend" / "app", root / "scripts", root / "web" / "src", root / "mobile" / "src")
    excluded = {
        Path(__file__).resolve(),
        Path(__file__).with_name("legacy_cleanup_manifest.py").resolve(),
        (root / "scripts" / "legacy_schema_cleanup_20260908.py").resolve(),
    }
    findings = []
    for source_root in source_roots:
        if not source_root.exists():
            continue
        for path in source_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in RUNTIME_SOURCE_SUFFIXES:
                continue
            if path.resolve() in excluded or "__pycache__" in path.parts:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for line_number, line in enumerate(content.splitlines(), 1):
                if INDEX_HINT_PATTERN.search(line) or any(name in line for name in LEGACY_INDEX_NAMES):
                    findings.append(f"{path.relative_to(root)}:{line_number}")
    return sorted(findings)


def validate_backup_proof(path: Path) -> list[str]:
    """Validate evidence created by a separate backup process; never run backups."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        backup = Path(payload["backup_path"])
        created_at = datetime.fromisoformat(payload["created_at"])
        if created_at.tzinfo is None:
            return ["backup proof timestamp must include timezone"]
        if payload["command_exit_code"] != 0:
            return ["backup command did not exit successfully"]
        if payload["revision"] != LEGACY_REVISION:
            return ["backup proof revision mismatch"]
        if not backup.is_absolute() or not backup.is_file():
            return ["backup file is unavailable"]
        actual_size = backup.stat().st_size
        if actual_size <= 0 or actual_size != payload["size"]:
            return ["backup size proof mismatch"]
        digest = hashlib.sha256()
        with backup.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != payload["sha256"]:
            return ["backup checksum proof mismatch"]
        if datetime.now(UTC) - created_at.astimezone(UTC) > MAX_BACKUP_AGE:
            return ["backup proof is older than the allowed window"]
    except Exception as exc:  # noqa: BLE001 -- do not expose paths or file contents.
        return [f"backup proof could not be validated ({type(exc).__name__})"]
    return []


def execute_ddl(engine, operation: LegacyCleanupOperation) -> None:
    """Execute one reviewed atomic DDL statement in its own autocommit boundary."""
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f"SET SESSION lock_wait_timeout = {DDL_LOCK_WAIT_SECONDS}")
        connection.exec_driver_sql(operation.forward_sql)


def _failure_result(
    completed: list[LegacyCleanupOperation],
    blockers: list[str],
    failure: str = "",
    executed_sql: list[str] | None = None,
) -> CleanupApplyResult:
    return CleanupApplyResult(
        status="CLEANUP BLOCKED",
        completed=[operation.key for operation in completed],
        executed_sql=executed_sql or [],
        recovery_sql=[operation.recovery_sql for operation in reversed(completed)],
        blockers=blockers,
        failure=failure,
    )


def apply_cleanup(
    engine,
    base,
    *,
    backup_proof: Path,
    expected_fingerprint: str,
    snapshot_loader: Callable = collect_cleanup_snapshot,
    ddl_executor: Callable = execute_ddl,
) -> CleanupApplyResult:
    """Apply reviewed operations one by one. This function never stamps Alembic."""
    backup_errors = validate_backup_proof(backup_proof)
    if backup_errors:
        return _failure_result([], backup_errors)

    return _apply_reviewed_operations(
        engine,
        base,
        expected_fingerprint=expected_fingerprint,
        snapshot_loader=snapshot_loader,
        ddl_executor=ddl_executor,
    )


def _apply_reviewed_operations(
    engine,
    base,
    *,
    expected_fingerprint: str,
    snapshot_loader: Callable = collect_cleanup_snapshot,
    ddl_executor: Callable = execute_ddl,
) -> CleanupApplyResult:
    """Internal state machine; the public apply entry validates backup evidence first."""

    completed: list[LegacyCleanupOperation] = []
    executed_sql: list[str] = []
    try:
        initial = assess_snapshot(snapshot_loader(engine, base, check_busy=True))
    except Exception as exc:  # noqa: BLE001 -- state collection must fail closed.
        return _failure_result(
            [],
            ["initial pre-check could not complete"],
            failure=type(exc).__name__,
        )
    if initial.blockers:
        return _failure_result([], initial.blockers)
    if initial.status == "ALREADY CLEAN":
        return CleanupApplyResult(status="ALREADY CLEAN")
    if initial.plan_fingerprint != expected_fingerprint:
        return _failure_result([], ["plan fingerprint mismatch"])

    for operation in LEGACY_CLEANUP_OPERATIONS:
        try:
            before = assess_snapshot(snapshot_loader(engine, base, check_busy=True))
        except Exception as exc:  # noqa: BLE001 -- state collection must fail closed.
            return _failure_result(
                completed,
                [f"pre-check failed: {operation.table}.{operation.index}"],
                failure=type(exc).__name__,
                executed_sql=executed_sql,
            )
        if before.blockers:
            return _failure_result(completed, before.blockers, executed_sql=executed_sql)
        if operation.key not in {item.key for item in before.pending}:
            continue
        try:
            ddl_executor(engine, operation)
            executed_sql.append(operation.forward_sql)
        except Exception as exc:  # noqa: BLE001 -- report class only; SQL/credentials stay hidden.
            return _failure_result(
                completed,
                [f"operation failed: {operation.table}.{operation.index}"],
                failure=type(exc).__name__,
                executed_sql=executed_sql,
            )
        try:
            after = assess_snapshot(snapshot_loader(engine, base, check_busy=True))
        except Exception as exc:  # noqa: BLE001 -- DDL succeeded; recovery is now required.
            completed.append(operation)
            return _failure_result(
                completed,
                [f"post-check failed: {operation.table}.{operation.index}"],
                failure=type(exc).__name__,
                executed_sql=executed_sql,
            )
        if after.blockers or operation.key in {item.key for item in after.pending}:
            blockers = after.blockers or [f"post-check failed: {operation.table}.{operation.index}"]
            completed.append(operation)
            return _failure_result(completed, blockers, executed_sql=executed_sql)
        completed.append(operation)

    try:
        final = assess_snapshot(snapshot_loader(engine, base, check_busy=True))
    except Exception as exc:  # noqa: BLE001 -- report recovery without leaking details.
        return _failure_result(
            completed,
            ["final verification could not complete"],
            failure=type(exc).__name__,
            executed_sql=executed_sql,
        )
    if final.blockers or final.status != "ALREADY CLEAN":
        blockers = final.blockers or ["final schema is not clean"]
        return _failure_result(completed, blockers, executed_sql=executed_sql)
    return CleanupApplyResult(
        status="LEGACY CLEANUP COMPLETE",
        completed=[operation.key for operation in completed],
        executed_sql=executed_sql,
        recovery_sql=[operation.recovery_sql for operation in reversed(completed)],
    )
