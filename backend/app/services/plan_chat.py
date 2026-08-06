from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models import PlanChatMessage, PlanChatSession, PlanItem, StudyPlan
from app.services.ai_gateway import AIModelGateway, extract_json
from app.services.study_planner import _normalize, generate_study_plan

SYSTEM_PROMPT = (
    "你是AI智学管家的专属学习规划顾问。你的任务是通过对话逐步收集用户信息，"
    "一次只问一个问题，不要一次问多个问题。"
    "需要收集的关键信息包括：专业与年级、学习目标、每日可用时间、计划周期、重点科目、薄弱点、学习偏好。"
    "当信息足够时，只输出如下 JSON 草稿，不要输出其他内容："
    '{"draft": {"title": "...", "goal": "...", "items": ['
    '{"title": "...", "subject": "...", "scheduled_date": "YYYY-MM-DD", '
    '"duration_minutes": 60, "order_index": 1}]}}'
    "如果用户对已有草稿提出修改，请结合草稿和用户要求输出新的 JSON 草稿。"
)

FIELD_QUESTIONS: list[tuple[str, str]] = [
    ("major", "你的专业和年级是什么？"),
    ("goal", "你这次想达成的学习目标是什么？（例如通过四级、掌握数据结构、期末不挂科）"),
    ("daily_minutes", "你每天大约能投入多少分钟学习？"),
    ("weeks", "你希望这个计划覆盖几周？"),
    ("subjects", "这段时间的重点科目有哪些？（用逗号分隔）"),
    ("weak_points", "你目前最薄弱的知识点或最想加强的部分是什么？"),
    ("learning_style", "你更喜欢哪种学习方式？看视频、做题、读教材还是混合？"),
]


def _load_context(session: PlanChatSession) -> dict[str, str]:
    try:
        data = json.loads(session.collected_context or "{}")
        return {key: str(value) for key, value in data.items()} if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _save_context(session: PlanChatSession, context: dict[str, str]) -> None:
    session.collected_context = json.dumps(context, ensure_ascii=False)


def _first_missing(context: dict[str, str]) -> str | None:
    for key, _ in FIELD_QUESTIONS:
        if not context.get(key):
            return key
    return None


def _question_for(key: str) -> str:
    for question_key, question in FIELD_QUESTIONS:
        if question_key == key:
            return question
    return "请继续补充你的学习情况。"


def _build_messages(session: PlanChatSession) -> list[dict[str, str]]:
    return [{"role": message.role, "content": message.content} for message in session.messages]


def _extract_int(value: str | None, default: int) -> int:
    match = re.search(r"\d+", value or "")
    if not match:
        return default
    return max(1, min(int(match.group(0)), 600))


def _normalize_draft(data: dict[str, Any], fallback_title: str) -> dict[str, Any]:
    normalized = _normalize(
        {
            "title": data.get("title") or fallback_title,
            "goal": data.get("goal"),
            "items": data.get("items", []),
        },
        "",
        "",
    )
    if not normalized["items"]:
        raise ValueError("draft items empty")
    return normalized


def _force_draft(context: dict[str, str]) -> dict[str, Any]:
    major = context.get("major") or "综合学习"
    goal = context.get("goal") or "掌握专业知识"
    daily_minutes = _extract_int(context.get("daily_minutes"), 60)
    weeks = min(_extract_int(context.get("weeks"), 4), 12)
    subjects = [
        item.strip()
        for item in re.split(r"[,，、;；]", context.get("subjects", ""))
        if item.strip()
    ]
    return generate_study_plan(major, "", goal, daily_minutes, weeks, subjects)


def start_chat(db: Session, user_id: int) -> tuple[PlanChatSession, str]:
    session = PlanChatSession(user_id=user_id, status="collecting")
    db.add(session)
    db.flush()
    first_question = _question_for("major")
    db.add(
        PlanChatMessage(
            session_id=session.id,
            role="assistant",
            content=first_question,
        )
    )
    db.commit()
    db.refresh(session)
    return session, first_question


def process_message(
    db: Session,
    session: PlanChatSession,
    user_content: str,
) -> dict[str, Any]:
    context = _load_context(session)
    missing_key = _first_missing(context)
    if missing_key:
        context[missing_key] = user_content.strip()
        _save_context(session, context)

    db.add(
        PlanChatMessage(
            session_id=session.id,
            role="user",
            content=user_content,
        )
    )
    db.flush()

    messages = _build_messages(session)
    text = AIModelGateway().chat(
        [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
        temperature=0.4,
    )
    data = extract_json(text)

    if (
        isinstance(data, dict)
        and isinstance(data.get("draft"), dict)
        and data["draft"].get("items")
    ):
        try:
            draft = _normalize_draft(data["draft"], "AI 对话学习计划")
        except ValueError:
            draft = None
        if draft:
            session.draft_json = json.dumps(draft, ensure_ascii=False)
            session.status = "draft_ready"
            reply = "草稿已经生成，请确认或继续提出修改。"
            db.add(
                PlanChatMessage(
                    session_id=session.id,
                    role="assistant",
                    content=reply,
                )
            )
            db.commit()
            return {"reply": reply, "status": session.status, "draft": draft}

    reply = text.strip()
    offline = not reply or "离线降级响应" in reply
    user_turns = sum(1 for message in session.messages if message.role == "user")
    if not offline and (_first_missing(context) is None or user_turns >= 10):
        draft = _force_draft(context)
        session.draft_json = json.dumps(draft, ensure_ascii=False)
        session.status = "draft_ready"
        reply = "草稿已经生成，请确认或继续提出修改。"
        db.add(
            PlanChatMessage(
                session_id=session.id,
                role="assistant",
                content=reply,
            )
        )
        db.commit()
        return {"reply": reply, "status": session.status, "draft": draft}

    if offline:
        missing_key = _first_missing(context)
        if missing_key:
            reply = _question_for(missing_key)
        else:
            draft = _force_draft(context)
            session.draft_json = json.dumps(draft, ensure_ascii=False)
            session.status = "draft_ready"
            reply = "草稿已经生成，请确认或继续提出修改。"
            db.add(
                PlanChatMessage(
                    session_id=session.id,
                    role="assistant",
                    content=reply,
                )
            )
            db.commit()
            return {"reply": reply, "status": session.status, "draft": draft}

    db.add(
        PlanChatMessage(
            session_id=session.id,
            role="assistant",
            content=reply,
        )
    )
    db.commit()
    return {"reply": reply, "status": session.status, "draft": None}


def confirm_chat(db: Session, session: PlanChatSession) -> StudyPlan:
    if session.status != "draft_ready" or not session.draft_json:
        raise ValueError("当前会话还没有可确认的学习计划草稿")
    draft = json.loads(session.draft_json)
    items = draft.get("items", [])
    start = date.today()
    end = start + timedelta(weeks=4)
    for item in items:
        try:
            scheduled = date.fromisoformat(item.get("scheduled_date", ""))
        except ValueError:
            continue
        end = max(end, scheduled)

    plan = StudyPlan(
        user_id=session.user_id,
        title=draft.get("title") or "AI 对话学习计划",
        goal=draft.get("goal"),
        start_date=start,
        end_date=end,
        status="active",
    )
    for index, item in enumerate(items, start=1):
        plan.items.append(
            PlanItem(
                title=item.get("title") or f"学习任务 {index}",
                subject=item.get("subject"),
                scheduled_date=date.fromisoformat(item.get("scheduled_date", start.isoformat())),
                duration_minutes=int(item.get("duration_minutes") or 60),
                order_index=int(item.get("order_index") or index),
            )
        )
    session.status = "confirmed"
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan
