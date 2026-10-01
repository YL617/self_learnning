"""错题复习调度（第一版：可解释的固定间隔）。

间隔表是全局唯一来源；answers 路由与 wrong-book 路由都复用它，
避免出现第二套复习规则。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

# 复习阶段 → 间隔天数
REVIEW_INTERVALS: dict[int, int] = {1: 1, 2: 3, 3: 7, 4: 15, 5: 30}
INITIAL_REVIEW_STAGE = 1
MAX_REVIEW_STAGE = max(REVIEW_INTERVALS)
# 到达最高阶段后再次答对即视为已掌握
MASTERED_STAGE = MAX_REVIEW_STAGE


def interval_days(stage: int) -> int:
    bounded = min(max(stage, INITIAL_REVIEW_STAGE), MAX_REVIEW_STAGE)
    return REVIEW_INTERVALS[bounded]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def schedule_first_review(item, today: date) -> None:
    """首次答错：进入复习队列，stage=1。"""
    item.review_stage = INITIAL_REVIEW_STAGE
    item.next_review_date = today + timedelta(days=interval_days(INITIAL_REVIEW_STAGE))


def apply_review_outcome(
    item,
    *,
    correct: bool,
    today: date,
    now: datetime | None = None,
) -> None:
    """一次复习结果对错题项的影响。

    答对：阶段前进，下次复习时间延后；到达最高阶段后再次答对 → mastered。
    答错：阶段回退一级（不低于 1），下次复习时间提前。
    """
    moment = now or _now()
    item.review_count += 1
    item.last_reviewed_at = moment
    if correct:
        if item.review_stage >= MASTERED_STAGE:
            item.mastered = True
            item.next_review_date = today + timedelta(days=interval_days(MASTERED_STAGE))
        else:
            item.review_stage = min(item.review_stage + 1, MAX_REVIEW_STAGE)
            item.next_review_date = today + timedelta(days=interval_days(item.review_stage))
    else:
        item.review_stage = max(INITIAL_REVIEW_STAGE, item.review_stage - 1)
        item.next_review_date = today + timedelta(days=interval_days(item.review_stage))


def reset_for_relearn(item, today: date) -> None:
    """取消掌握：重新回到复习队列第 1 阶段。"""
    item.mastered = False
    item.review_stage = INITIAL_REVIEW_STAGE
    item.next_review_date = today + timedelta(days=interval_days(INITIAL_REVIEW_STAGE))


__all__ = [
    "INITIAL_REVIEW_STAGE",
    "MASTERED_STAGE",
    "MAX_REVIEW_STAGE",
    "REVIEW_INTERVALS",
    "apply_review_outcome",
    "interval_days",
    "reset_for_relearn",
    "schedule_first_review",
]
