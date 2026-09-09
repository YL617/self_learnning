"""Reviewed one-time cleanup contract for the 20260908 legacy production schema.

This manifest is deliberately not a general-purpose schema repair definition.
It is shared by the cleanup CLI, tests, and the recovery report.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

LEGACY_REVISION = "20260908_001"
TARGET_REVISION = "20260909_001"


@dataclass(frozen=True)
class LegacyCleanupOperation:
    operation: Literal["create", "drop"]
    table: str
    index: str
    columns: tuple[str, ...]
    unique: bool
    forward_sql: str
    recovery_sql: str
    reason: str
    expected_drift_error: str

    @property
    def key(self) -> str:
        return f"{self.operation}:{self.table}.{self.index}"


LEGACY_CLEANUP_OPERATIONS: tuple[LegacyCleanupOperation, ...] = (
    LegacyCleanupOperation(
        operation="create",
        table="course_recommendations",
        index="ix_course_recommendations_status",
        columns=("status",),
        unique=False,
        forward_sql=(
            "ALTER TABLE `course_recommendations` "
            "ADD INDEX `ix_course_recommendations_status` (`status`), "
            "ALGORITHM=INPLACE, LOCK=NONE"
        ),
        recovery_sql=(
            "ALTER TABLE `course_recommendations` "
            "DROP INDEX `ix_course_recommendations_status`, "
            "ALGORITHM=INPLACE, LOCK=NONE"
        ),
        reason="ORM and fresh reconciliation require a non-unique status index",
        expected_drift_error=(
            "INDEX MISMATCH course_recommendations: "
            "db=[('course_id',), ('plan_id',), ('user_id',)] "
            "orm=[('course_id',), ('plan_id',), ('status',), ('user_id',)]"
        ),
    ),
    LegacyCleanupOperation(
        operation="drop",
        table="activation_codes",
        index="ix_activation_codes_id",
        columns=("id",),
        unique=False,
        forward_sql=(
            "ALTER TABLE `activation_codes` DROP INDEX `ix_activation_codes_id`, "
            "ALGORITHM=INPLACE, LOCK=NONE"
        ),
        recovery_sql=(
            "ALTER TABLE `activation_codes` ADD INDEX `ix_activation_codes_id` (`id`), "
            "ALGORITHM=INPLACE, LOCK=NONE"
        ),
        reason="Legacy redundant secondary index duplicates PRIMARY(id)",
        expected_drift_error="INDEX MISMATCH activation_codes: db=[('id',)] orm=[]",
    ),
    LegacyCleanupOperation(
        operation="drop",
        table="ai_provider_snapshots",
        index="ix_ai_provider_snapshots_id",
        columns=("id",),
        unique=False,
        forward_sql=(
            "ALTER TABLE `ai_provider_snapshots` "
            "DROP INDEX `ix_ai_provider_snapshots_id`, "
            "ALGORITHM=INPLACE, LOCK=NONE"
        ),
        recovery_sql=(
            "ALTER TABLE `ai_provider_snapshots` "
            "ADD INDEX `ix_ai_provider_snapshots_id` (`id`), "
            "ALGORITHM=INPLACE, LOCK=NONE"
        ),
        reason="Legacy redundant secondary index duplicates PRIMARY(id)",
        expected_drift_error=(
            "INDEX MISMATCH ai_provider_snapshots: "
            "db=[('id',), ('provider',)] orm=[('provider',)]"
        ),
    ),
    LegacyCleanupOperation(
        operation="drop",
        table="pet_messages",
        index="ix_pet_messages_id",
        columns=("id",),
        unique=False,
        forward_sql=(
            "ALTER TABLE `pet_messages` DROP INDEX `ix_pet_messages_id`, "
            "ALGORITHM=INPLACE, LOCK=NONE"
        ),
        recovery_sql=(
            "ALTER TABLE `pet_messages` ADD INDEX `ix_pet_messages_id` (`id`), "
            "ALGORITHM=INPLACE, LOCK=NONE"
        ),
        reason="Legacy redundant secondary index duplicates PRIMARY(id)",
        expected_drift_error=(
            "INDEX MISMATCH pet_messages: db=[('id',), ('pet_id',)] orm=[('pet_id',)]"
        ),
    ),
    LegacyCleanupOperation(
        operation="drop",
        table="pet_play_sessions",
        index="ix_pet_play_sessions_id",
        columns=("id",),
        unique=False,
        forward_sql=(
            "ALTER TABLE `pet_play_sessions` DROP INDEX `ix_pet_play_sessions_id`, "
            "ALGORITHM=INPLACE, LOCK=NONE"
        ),
        recovery_sql=(
            "ALTER TABLE `pet_play_sessions` ADD INDEX `ix_pet_play_sessions_id` (`id`), "
            "ALGORITHM=INPLACE, LOCK=NONE"
        ),
        reason="Legacy redundant secondary index duplicates PRIMARY(id)",
        expected_drift_error=(
            "INDEX MISMATCH pet_play_sessions: db=[('id',), ('pet_id',)] orm=[('pet_id',)]"
        ),
    ),
    LegacyCleanupOperation(
        operation="drop",
        table="plan_chat_messages",
        index="ix_plan_chat_messages_id",
        columns=("id",),
        unique=False,
        forward_sql=(
            "ALTER TABLE `plan_chat_messages` DROP INDEX `ix_plan_chat_messages_id`, "
            "ALGORITHM=INPLACE, LOCK=NONE"
        ),
        recovery_sql=(
            "ALTER TABLE `plan_chat_messages` ADD INDEX `ix_plan_chat_messages_id` (`id`), "
            "ALGORITHM=INPLACE, LOCK=NONE"
        ),
        reason="Legacy redundant secondary index duplicates PRIMARY(id)",
        expected_drift_error=(
            "INDEX MISMATCH plan_chat_messages: "
            "db=[('id',), ('session_id',)] orm=[('session_id',)]"
        ),
    ),
    LegacyCleanupOperation(
        operation="drop",
        table="plan_chat_sessions",
        index="ix_plan_chat_sessions_id",
        columns=("id",),
        unique=False,
        forward_sql=(
            "ALTER TABLE `plan_chat_sessions` DROP INDEX `ix_plan_chat_sessions_id`, "
            "ALGORITHM=INPLACE, LOCK=NONE"
        ),
        recovery_sql=(
            "ALTER TABLE `plan_chat_sessions` ADD INDEX `ix_plan_chat_sessions_id` (`id`), "
            "ALGORITHM=INPLACE, LOCK=NONE"
        ),
        reason="Legacy redundant secondary index duplicates PRIMARY(id)",
        expected_drift_error=(
            "INDEX MISMATCH plan_chat_sessions: "
            "db=[('id',), ('user_id',)] orm=[('user_id',)]"
        ),
    ),
)

TARGET_TABLES = frozenset(operation.table for operation in LEGACY_CLEANUP_OPERATIONS)
LEGACY_INDEX_NAMES = frozenset(
    operation.index for operation in LEGACY_CLEANUP_OPERATIONS if operation.operation == "drop"
)


def legacy_cleanup_manifest() -> dict[str, object]:
    """Return a serialization-friendly copy for reports and external checks."""
    return {
        "legacy_revision": LEGACY_REVISION,
        "target_revision": TARGET_REVISION,
        "operations": [
            {
                "operation": operation.operation,
                "table": operation.table,
                "index": operation.index,
                "columns": list(operation.columns),
                "unique": operation.unique,
                "forward_sql": operation.forward_sql,
                "recovery_sql": operation.recovery_sql,
                "reason": operation.reason,
            }
            for operation in LEGACY_CLEANUP_OPERATIONS
        ],
    }
