from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ActivationCode, AiDailyUsage, User

TIER_ORDER = {"free": 0, "basic": 1, "advanced": 2, "full": 3}
TIER_NAMES = {
    "free": "免费版",
    "basic": "基础会员",
    "advanced": "进阶会员",
    "full": "完整会员",
}


class MembershipRequired(Exception):
    pass


class QuotaExceeded(Exception):
    pass


class ActivationCodeError(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def is_trial_active(user: User) -> bool:
    created = _as_aware(user.created_at)
    if created is None:
        return False
    trial_days = get_settings().TRIAL_DAYS
    return _utcnow() < created + timedelta(days=trial_days)


def get_effective_membership(user: User) -> str:
    expires = _as_aware(user.membership_expires_at)
    if expires is not None and expires <= _utcnow():
        return "free"
    return user.membership_level


def has_membership(user: User, min_tier: str) -> bool:
    if is_trial_active(user):
        return True
    return TIER_ORDER.get(get_effective_membership(user), 0) >= TIER_ORDER.get(
        min_tier, 0
    )


def daily_ai_quota(user: User) -> int:
    settings = get_settings()
    tier = get_effective_membership(user)
    if tier == "full":
        return settings.FULL_DAILY_AI_QUOTA
    if tier == "advanced":
        return settings.ADVANCED_DAILY_AI_QUOTA
    if tier == "basic":
        return settings.BASIC_DAILY_AI_QUOTA
    return settings.FREE_DAILY_AI_QUOTA


def get_ai_usage_today(db: Session, user_id: int) -> int:
    row = db.scalar(
        select(AiDailyUsage).where(
            AiDailyUsage.user_id == user_id,
            AiDailyUsage.usage_date == date.today(),
        )
    )
    return row.calls if row is not None else 0


def consume_ai_quota(db: Session, user: User) -> None:
    if get_ai_usage_today(db, user.id) >= daily_ai_quota(user):
        raise QuotaExceeded("今日 AI 调用次数已用完，请升级会员或明天再试")
    row = db.scalar(
        select(AiDailyUsage).where(
            AiDailyUsage.user_id == user.id,
            AiDailyUsage.usage_date == date.today(),
        )
    )
    if row is None:
        row = AiDailyUsage(user_id=user.id, usage_date=date.today(), calls=1)
        db.add(row)
    else:
        row.calls += 1
    db.flush()


def activate_code(db: Session, user: User, code_value: str) -> None:
    code = db.scalar(
        select(ActivationCode).where(ActivationCode.code == code_value.strip())
    )
    if code is None:
        raise ActivationCodeError("激活码不存在")
    if code.status != "unused":
        raise ActivationCodeError("激活码已使用或已撤销")
    if code.tier not in TIER_ORDER:
        raise ActivationCodeError("激活码档位无效")

    now = _utcnow()
    current_expiry = _as_aware(user.membership_expires_at)
    base = current_expiry if current_expiry is not None and current_expiry > now else now
    user.membership_level = code.tier
    user.membership_expires_at = (base + timedelta(days=code.days)).replace(tzinfo=None)
    code.status = "used"
    code.used_by = user.id
    code.used_at = now.replace(tzinfo=None)
    db.flush()
