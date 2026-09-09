"""机器可读的 Schema Reconciliation Manifest。

供 migration test / drift checker / adoption inspector 共用，避免三套逻辑各写一份。
仅描述 20260909_001 schema_reconciliation 负责的对象与已知 server_default 差异。
"""

import json
from pathlib import Path

# 由 reconciliation 单独创建、绝不允许重复创建的整表
RECONCILED_TABLES: list[str] = [
    "todos",
    "reminders",
    "shop_items",
    "plan_adjustment_logs",
    "file_analyze_results",
]

# 由 reconciliation 单独增加的列；这些列在 Fresh 链中由 20260909_001 补齐
RECONCILED_COLUMNS: dict[str, list[str]] = {
    "plan_items": ["difficulty", "suggested_time_slot", "buffer_minutes"],
    "questions": ["is_favorite"],
    "wrong_book_items": ["review_stage", "next_review_date", "last_reviewed_at"],
    "documents": ["size_bytes", "temp_cleanup_at"],
    "pets": ["hunger", "evolution_stage", "runaway", "hunger_updated_at", "last_fed_at"],
    "users": ["checkin_streak", "last_checkin_date"],
}

# 由 reconciliation 增加的索引
RECONCILED_INDEXES: dict[str, list[str]] = {
    "course_recommendations": ["status"],
}

# server_default 字段级白名单。
# 键为 "table.column"；仅当 数据库存在 server_default 而 ORM 只有 Python-side default 时命中。
# 白名单外任何 server_default 差异都必须判定为 drift ERROR。
ALLOWED_SERVER_DEFAULT_DIFFS: dict[str, dict[str, str]] = {
    # ---- reconciliation 为 SQLite/MySQL 加 NOT NULL 列所需的 server_default ----
    "plan_items.difficulty": {"migration_default": "medium", "orm_default": "python: medium", "reason": "reconciliation NOT NULL 列兼容"},
    "plan_items.buffer_minutes": {"migration_default": "0", "orm_default": "python: 0", "reason": "reconciliation NOT NULL 列兼容"},
    "questions.is_favorite": {"migration_default": "0", "orm_default": "python: False", "reason": "reconciliation NOT NULL 列兼容"},
    "wrong_book_items.review_stage": {"migration_default": "1", "orm_default": "python: 1", "reason": "reconciliation NOT NULL 列兼容"},
    "wrong_book_items.next_review_date": {"migration_default": "'1970-01-01'", "orm_default": "python: date.today", "reason": "reconciliation NOT NULL 列兼容"},
    "documents.size_bytes": {"migration_default": "0", "orm_default": "python: 0", "reason": "reconciliation NOT NULL 列兼容"},
    "pets.hunger": {"migration_default": "100", "orm_default": "python: 100", "reason": "reconciliation NOT NULL 列兼容"},
    "pets.evolution_stage": {"migration_default": "1", "orm_default": "python: 1", "reason": "reconciliation NOT NULL 列兼容"},
    "pets.runaway": {"migration_default": "0", "orm_default": "python: False", "reason": "reconciliation NOT NULL 列兼容"},
    "users.checkin_streak": {"migration_default": "0", "orm_default": "python: 0", "reason": "reconciliation NOT NULL 列兼容"},
    # ---- 历史迁移 server_default 与 ORM Python-side default 等价 ----
    "user_profiles.weekly_study_minutes": {"migration_default": "420", "orm_default": "python: 420", "reason": "历史迁移兼容"},
    "user_profiles.onboarding_completed": {"migration_default": "0", "orm_default": "python: False", "reason": "历史迁移兼容"},
    "users.membership_level": {"migration_default": "free", "orm_default": "python: free", "reason": "历史迁移兼容"},
    "users.role": {"migration_default": "user", "orm_default": "python: user", "reason": "历史迁移兼容"},
    "plan_chat_sessions.status": {"migration_default": "collecting", "orm_default": "python: collecting", "reason": "历史迁移兼容"},
    "pet_messages.role": {"migration_default": "assistant", "orm_default": "python: assistant", "reason": "历史迁移兼容"},
    "pet_messages.kind": {"migration_default": "chat", "orm_default": "python: chat", "reason": "历史迁移兼容"},
    "pets.play_count_today": {"migration_default": "0", "orm_default": "python: 0", "reason": "历史迁移兼容"},
    "pet_play_sessions.status": {"migration_default": "active", "orm_default": "python: active", "reason": "历史迁移兼容"},
    "pet_play_sessions.duration_minutes": {"migration_default": "15", "orm_default": "python: 15", "reason": "历史迁移兼容"},
    "pet_play_sessions.coin_cost": {"migration_default": "20", "orm_default": "python: 20", "reason": "历史迁移兼容"},
    "pet_play_sessions.mood_gain": {"migration_default": "15", "orm_default": "python: 15", "reason": "历史迁移兼容"},
    "pet_play_sessions.exp_gain": {"migration_default": "20", "orm_default": "python: 20", "reason": "历史迁移兼容"},
    "pet_play_sessions.hunger_loss": {"migration_default": "15", "orm_default": "python: 15", "reason": "历史迁移兼容"},
    "ai_provider_snapshots.total_balance": {"migration_default": "0", "orm_default": "python: 0", "reason": "历史迁移兼容"},
    "ai_provider_snapshots.granted_balance": {"migration_default": "0", "orm_default": "python: 0", "reason": "历史迁移兼容"},
    "ai_provider_snapshots.topped_up_balance": {"migration_default": "0", "orm_default": "python: 0", "reason": "历史迁移兼容"},
    "ai_provider_snapshots.is_available": {"migration_default": "1", "orm_default": "python: True", "reason": "历史迁移兼容"},
    "ai_provider_snapshots.status": {"migration_default": "ok", "orm_default": "python: ok", "reason": "历史迁移兼容"},
    "ai_usage_records.tokens": {"migration_default": "0", "orm_default": "python: 0", "reason": "历史迁移兼容"},
    "ai_usage_records.cost": {"migration_default": "0", "orm_default": "python: 0", "reason": "历史迁移兼容"},
    "activation_codes.status": {"migration_default": "unused", "orm_default": "python: unused", "reason": "历史迁移兼容"},
    "ai_daily_usage.calls": {"migration_default": "0", "orm_default": "python: 0", "reason": "历史迁移兼容"},
    "focus_tags.color": {"migration_default": "#0f766e", "orm_default": "python: #0f766e", "reason": "历史迁移兼容"},
    "course_recommendations.platform": {"migration_default": "在线课程", "orm_default": "python: 在线课程", "reason": "历史迁移兼容"},
    "course_recommendations.status": {"migration_default": "pending", "orm_default": "python: pending", "reason": "历史迁移兼容"},
    "courses.dismiss_count": {"migration_default": "0", "orm_default": "python: 0", "reason": "历史迁移兼容"},
    "courses.save_count": {"migration_default": "0", "orm_default": "python: 0", "reason": "历史迁移兼容"},
    "knowledge_points.status": {"migration_default": "active", "orm_default": "python: active", "reason": "历史迁移兼容"},
    "knowledge_points.source": {"migration_default": "system", "orm_default": "python: system", "reason": "历史迁移兼容"},
}

# Explicit table/column identity is included in every exception for machine consumers.
for _key, _entry in ALLOWED_SERVER_DEFAULT_DIFFS.items():
    _entry["table"], _entry["column"] = _key.split(".", 1)


def reconciliation_manifest():
    """Frozen structures include types, PK/FK, nullability, defaults and indexes.

    The pre-reconciliation contract owns ALL its objects. Reconciliation may only
    add the enumerated delta, never recreate those historical managed objects.
    """
    profiles = json.loads(Path(__file__).with_name("schema_profiles.json").read_text(encoding="utf-8"))
    before, after = profiles["20260908_001"], profiles["20260909_001"]
    return {
        "revision": "20260909_001",
        "created_tables": {t: after[t] for t in RECONCILED_TABLES},
        "added_columns": {
            t: [c for c in after[t]["columns"] if c["name"] in names]
            for t, names in RECONCILED_COLUMNS.items()
        },
        "added_indexes": {
            t: [i for i in after[t]["indexes"] if i["name"] in
                {f"ix_{t}_{name}" for name in names}]
            for t, names in RECONCILED_INDEXES.items()
        },
        "historical_managed_objects": before,
    }
