from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import create_engine, event, text

from app.core.database import Base
from app.core.legacy_cleanup import (
    ADOPTION_MISMATCH_REASON,
    CleanupSnapshot,
    IndexSnapshot,
    _apply_reviewed_operations,
    assess_snapshot,
    collect_cleanup_snapshot,
    scan_repository_index_dependencies,
)
from app.core.legacy_cleanup_manifest import (
    LEGACY_CLEANUP_OPERATIONS,
    LEGACY_REVISION,
    TARGET_REVISION,
    legacy_cleanup_manifest,
)

TARGET_TABLES = {operation.table for operation in LEGACY_CLEANUP_OPERATIONS}


def _index(operation) -> IndexSnapshot:
    return IndexSnapshot(
        name=operation.index,
        columns=operation.columns,
        unique=operation.unique,
        index_type="BTREE",
        visible=True,
        sub_parts=tuple(None for _ in operation.columns),
    )


def _snapshot(
    *,
    completed: set[str] | None = None,
    dialect: str = "mysql",
    revision: str = LEGACY_REVISION,
    busy_reasons: tuple[str, ...] = (),
) -> CleanupSnapshot:
    completed = completed or set()
    indexes: dict[str, dict[str, IndexSnapshot]] = {table: {} for table in TARGET_TABLES}
    pending_errors = []
    for operation in LEGACY_CLEANUP_OPERATIONS:
        is_complete = operation.key in completed
        exists = is_complete if operation.operation == "create" else not is_complete
        if exists:
            indexes[operation.table][operation.index] = _index(operation)
        if not is_complete:
            pending_errors.append(operation.expected_drift_error)
    adoption_status = (
        f"SAFE TO ADOPT TO {TARGET_REVISION}"
        if not pending_errors
        else "ADOPTION BLOCKED"
    )
    adoption_reasons = (
        ()
        if not pending_errors
        else (ADOPTION_MISMATCH_REASON, *pending_errors)
    )
    return CleanupSnapshot(
        dialect=dialect,
        revision_rows=(revision,),
        tables=frozenset(TARGET_TABLES),
        table_engines={table: "InnoDB" for table in TARGET_TABLES},
        indexes=indexes,
        primary_keys={table: ("id",) for table in TARGET_TABLES},
        constrained_fk_columns={table: () for table in TARGET_TABLES},
        constraint_names=frozenset((table, "PRIMARY") for table in TARGET_TABLES),
        drift_errors=tuple(pending_errors),
        adoption_status=adoption_status,
        adoption_reasons=tuple(adoption_reasons),
        busy_reasons=busy_reasons,
    )


def test_dry_run_identifies_exactly_seven_operations():
    assessment = assess_snapshot(_snapshot())
    assert assessment.status == "LEGACY CLEANUP REQUIRED"
    assert assessment.exit_code == 0
    assert len(assessment.pending) == 7
    assert assessment.blockers == []


def test_already_clean_is_safe_and_has_no_pending_operations():
    completed = {operation.key for operation in LEGACY_CLEANUP_OPERATIONS}
    assessment = assess_snapshot(_snapshot(completed=completed))
    assert assessment.status == "ALREADY CLEAN"
    assert assessment.pending == []
    assert assessment.exit_code == 0


def test_wrong_revision_blocks():
    assessment = assess_snapshot(_snapshot(revision="20260907_001"))
    assert assessment.status == "CLEANUP BLOCKED"
    assert any("revision" in reason.lower() for reason in assessment.blockers)


def test_missing_drop_index_plus_other_drift_blocks():
    operation = next(op for op in LEGACY_CLEANUP_OPERATIONS if op.operation == "drop")
    snapshot = _snapshot(completed={operation.key})
    snapshot = replace(snapshot, drift_errors=(*snapshot.drift_errors, "MISSING TABLE users"))
    assert assess_snapshot(snapshot).status == "CLEANUP BLOCKED"


def test_same_name_with_different_columns_blocks():
    snapshot = _snapshot()
    operation = next(op for op in LEGACY_CLEANUP_OPERATIONS if op.operation == "drop")
    snapshot.indexes[operation.table][operation.index] = replace(
        _index(operation), columns=("id", "status")
    )
    assert assess_snapshot(snapshot).status == "CLEANUP BLOCKED"


def test_drop_index_that_is_unique_blocks():
    snapshot = _snapshot()
    operation = next(op for op in LEGACY_CLEANUP_OPERATIONS if op.operation == "drop")
    snapshot.indexes[operation.table][operation.index] = replace(
        _index(operation), unique=True
    )
    assert assess_snapshot(snapshot).status == "CLEANUP BLOCKED"


def test_missing_primary_key_blocks():
    snapshot = _snapshot()
    operation = next(op for op in LEGACY_CLEANUP_OPERATIONS if op.operation == "drop")
    snapshot.primary_keys[operation.table] = ()
    assert assess_snapshot(snapshot).status == "CLEANUP BLOCKED"


def test_wrong_status_index_blocks():
    snapshot = _snapshot()
    operation = next(op for op in LEGACY_CLEANUP_OPERATIONS if op.operation == "create")
    snapshot.indexes[operation.table][operation.index] = replace(
        _index(operation), columns=("status", "user_id")
    )
    assert assess_snapshot(snapshot).status == "CLEANUP BLOCKED"


def test_equivalent_status_index_with_other_name_blocks():
    snapshot = _snapshot()
    operation = next(op for op in LEGACY_CLEANUP_OPERATIONS if op.operation == "create")
    snapshot.indexes[operation.table]["legacy_status_idx"] = replace(
        _index(operation), name="legacy_status_idx"
    )
    assert assess_snapshot(snapshot).status == "CLEANUP BLOCKED"


def test_extra_real_drift_blocks():
    snapshot = replace(_snapshot(), drift_errors=(*_snapshot().drift_errors, "EXTRA TABLE x"))
    assert assess_snapshot(snapshot).status == "CLEANUP BLOCKED"


def test_non_mysql_blocks_apply_preflight():
    assessment = assess_snapshot(_snapshot(dialect="sqlite"))
    assert assessment.status == "CLEANUP BLOCKED"


@pytest.mark.parametrize(
    "reason",
    ("long transaction", "pending metadata lock", "active target DDL"),
)
def test_database_busy_blocks(reason):
    assessment = assess_snapshot(_snapshot(busy_reasons=(reason,)))
    assert assessment.status == "CLEANUP BLOCKED"
    assert any("DATABASE BUSY" in blocker for blocker in assessment.blockers)


def test_fk_that_requires_drop_index_blocks():
    snapshot = _snapshot()
    operation = next(op for op in LEGACY_CLEANUP_OPERATIONS if op.operation == "drop")
    snapshot.constrained_fk_columns[operation.table] = (("id",),)
    assert assess_snapshot(snapshot).status == "CLEANUP BLOCKED"


def test_apply_failure_reports_completed_and_recovery():
    completed: set[str] = set()
    calls = []

    def loader(_engine, _base, *, check_busy):
        assert check_busy is True
        return _snapshot(completed=completed)

    def executor(_engine, operation):
        calls.append(operation.key)
        if len(calls) == 3:
            raise RuntimeError("simulated DDL failure")
        completed.add(operation.key)

    initial = assess_snapshot(_snapshot())
    result = _apply_reviewed_operations(
        object(),
        object(),
        expected_fingerprint=initial.plan_fingerprint,
        snapshot_loader=loader,
        ddl_executor=executor,
    )
    assert result.status == "CLEANUP BLOCKED"
    assert result.completed == calls[:2]
    assert len(result.recovery_sql) == 2
    assert "RuntimeError" in result.failure
    assert "simulated" not in result.failure


def test_apply_completes_without_stamp():
    completed: set[str] = set()

    def loader(_engine, _base, *, check_busy):
        assert check_busy is True
        return _snapshot(completed=completed)

    def executor(_engine, operation):
        completed.add(operation.key)

    initial = assess_snapshot(_snapshot())
    result = _apply_reviewed_operations(
        object(),
        object(),
        expected_fingerprint=initial.plan_fingerprint,
        snapshot_loader=loader,
        ddl_executor=executor,
    )
    assert result.status == "LEGACY CLEANUP COMPLETE"
    assert len(result.completed) == 7
    assert all("stamp" not in operation.lower() for operation in result.executed_sql)


def test_post_check_failure_includes_just_executed_operation_recovery():
    completed: set[str] = set()
    load_count = 0

    def loader(_engine, _base, *, check_busy):
        nonlocal load_count
        assert check_busy is True
        load_count += 1
        if load_count == 3:
            raise RuntimeError("sensitive post-check details")
        return _snapshot(completed=completed)

    def executor(_engine, operation):
        completed.add(operation.key)

    initial = assess_snapshot(_snapshot())
    result = _apply_reviewed_operations(
        object(),
        object(),
        expected_fingerprint=initial.plan_fingerprint,
        snapshot_loader=loader,
        ddl_executor=executor,
    )
    first = LEGACY_CLEANUP_OPERATIONS[0]
    assert result.status == "CLEANUP BLOCKED"
    assert result.completed == [first.key]
    assert result.recovery_sql == [first.recovery_sql]
    assert result.failure == "RuntimeError"
    assert "sensitive" not in result.failure


def test_runtime_repository_has_no_index_hint_or_legacy_name_dependencies():
    findings = scan_repository_index_dependencies()
    assert findings == []


def test_manifest_has_seven_forward_and_recovery_operations():
    manifest = legacy_cleanup_manifest()
    operations = manifest["operations"]
    assert len(operations) == 7
    assert sum(item["operation"] == "drop" for item in operations) == 6
    assert sum(item["operation"] == "create" for item in operations) == 1
    assert all(item["forward_sql"] and item["recovery_sql"] for item in operations)
    assert all("stamp" not in item["forward_sql"].lower() for item in operations)


def test_dry_run_collection_only_issues_read_statements():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": LEGACY_REVISION},
        )
    statements = []
    event.listen(
        engine,
        "before_cursor_execute",
        lambda _conn, _cursor, sql, _params, _context, _many: statements.append(sql),
    )
    try:
        collect_cleanup_snapshot(engine, Base, check_busy=False)
    finally:
        engine.dispose()
    assert statements
    assert all(sql.lstrip().upper().startswith(("SELECT", "PRAGMA")) for sql in statements)
