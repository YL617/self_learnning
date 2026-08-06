from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.services.ai_gateway import AIModelGateway

SYSTEM_PROMPT = (
    "你是高校学习规划专家。根据学生信息生成个性化学习计划。"
    "只输出 JSON，不要输出任何解释或 Markdown。"
    'JSON 结构：{"title": "...", "goal": "...", "items": ['
    '{"title": "...", "subject": "...", "scheduled_date": "YYYY-MM-DD", '
    '"duration_minutes": 60, "order_index": 1}]}'
)


def _build_user_prompt(
    major: str,
    grade: str,
    goal: str,
    daily_minutes: int,
    weeks: int,
    subjects: list[str],
) -> str:
    subject_text = "、".join(subjects) if subjects else "按专业核心课合理安排"
    return (
        f"专业：{major}\n"
        f"年级：{grade}\n"
        f"目标：{goal}\n"
        f"每日学习时长：{daily_minutes}分钟\n"
        f"周期：{weeks}周\n"
        f"重点科目：{subject_text}"
    )


def _default_items(
    major: str,
    daily_minutes: int,
    weeks: int,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    start = date.today()
    day = 0
    templates = ["专业基础复习", "核心知识点学习", "练习与错题整理", "周复盘与计划调整"]
    for week in range(1, weeks + 1):
        for base in templates:
            items.append(
                {
                    "title": f"第{week}周·{base}",
                    "subject": major or "综合学习",
                    "scheduled_date": (start + timedelta(days=day)).isoformat(),
                    "duration_minutes": daily_minutes,
                    "difficulty": "medium",
                    "suggested_time_slot": "晚间" if week % 2 == 0 else "上午",
                    "buffer_minutes": max(10, round(daily_minutes * 0.2)),
                    "order_index": len(items) + 1,
                }
            )
            day += 1
    return items


def _normalize(
    data: dict[str, Any],
    major: str,
    goal: str,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    raw_items = data.get("items", [])
    if not isinstance(raw_items, list):
        raw_items = []
    for idx, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue
        try:
            scheduled = date.fromisoformat(str(item.get("scheduled_date", "")))
        except ValueError:
            scheduled = date.today()
        items.append(
            {
                "title": str(item.get("title", "")).strip() or f"学习任务 {idx}",
                "subject": str(item.get("subject", major or "综合学习")).strip(),
                "scheduled_date": scheduled.isoformat(),
                "duration_minutes": max(10, int(item.get("duration_minutes") or 60)),
                "difficulty": str(item.get("difficulty", "medium")).strip() or "medium",
                "suggested_time_slot": str(item.get("suggested_time_slot", "")).strip() or None,
                "buffer_minutes": max(0, int(item.get("buffer_minutes") or 0)),
                "order_index": idx,
            }
        )
    return {
        "title": str(data.get("title", "")).strip() or f"{major or '综合'}学习计划",
        "goal": str(data.get("goal", "")).strip() or goal,
        "items": items,
    }


def generate_study_plan(
    major: str,
    grade: str,
    goal: str,
    daily_minutes: int,
    weeks: int,
    subjects: list[str],
) -> dict[str, Any]:
    gateway = AIModelGateway()
    user_prompt = _build_user_prompt(major, grade, goal, daily_minutes, weeks, subjects)
    data = gateway.generate_json(SYSTEM_PROMPT, user_prompt)
    if isinstance(data, dict) and isinstance(data.get("items"), list) and data["items"]:
        return _normalize(data, major, goal)
    return {
        "title": f"{major or '综合'}学习计划",
        "goal": goal,
        "items": _default_items(major, daily_minutes, weeks),
    }


def _lower_difficulty(difficulty: str) -> str:
    order = {"hard": "medium", "medium": "easy", "easy": "easy"}
    return order.get(difficulty, "medium")


def adjust_study_plan(plan: Any) -> tuple[str, dict]:
    """Rule-based adjustment: lighten overdue tasks and reward fast learners."""
    from app.models import PlanItem

    items = sorted(plan.items, key=lambda item: item.order_index)
    today = date.today()
    total = len(items)
    completed = sum(1 for item in items if item.completed)
    overdue = [
        item for item in items if not item.completed and item.scheduled_date < today
    ]

    before = [
        {
            "id": item.id,
            "title": item.title,
            "scheduled_date": item.scheduled_date.isoformat(),
            "duration_minutes": item.duration_minutes,
            "difficulty": item.difficulty,
            "suggested_time_slot": item.suggested_time_slot,
            "completed": item.completed,
        }
        for item in items
    ]

    changes: list[str] = []
    for item in overdue:
        item.scheduled_date = today + timedelta(days=1)
        item.duration_minutes = max(15, int(item.duration_minutes * 0.8))
        item.difficulty = _lower_difficulty(item.difficulty)
        item.suggested_time_slot = "周末"
        changes.append(f"「{item.title}」延后并减轻负担")

    if total and completed / total >= 0.8:
        last = items[-1] if items else None
        plan.items.append(
            PlanItem(
                plan_id=plan.id,
                title="拓展挑战任务",
                subject=items[0].subject if items else "综合",
                scheduled_date=today + timedelta(days=1),
                duration_minutes=45,
                difficulty="hard",
                suggested_time_slot="晚间",
                buffer_minutes=10,
                order_index=(last.order_index + 1 if last else 1),
            )
        )
        changes.append("新增拓展挑战任务")

    reason = "；".join(changes) if changes else "当前计划执行情况良好，无需调整"
    after_items = sorted(plan.items, key=lambda item: item.order_index)
    after = [
        {
            "id": item.id,
            "title": item.title,
            "scheduled_date": item.scheduled_date.isoformat(),
            "duration_minutes": item.duration_minutes,
            "difficulty": item.difficulty,
            "suggested_time_slot": item.suggested_time_slot,
            "completed": item.completed,
        }
        for item in after_items
    ]
    return reason, {
        "before": before,
        "after": after,
        "completed": completed,
        "total": total,
        "overdue": len(overdue),
    }
