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
    "你是AI智学管家的专属学习规划顾问，语气专业、温和、自然。你的任务是帮助用户制定详细、可执行的学习计划。\n"
    "规则：\n"
    "1. 一次只问一个问题，不要一次问多个问题。\n"
    "2. 绝对不要替用户回答或替用户做决定，用户回答后你只做追问和整理。\n"
    "3. 结合用户已经提供的信息持续追问，避免重复提问；需要时追问考试或截止时间、每周可学习时段、当前基础、薄弱点、偏好方式、计划周期等。\n"
    "4. 当你认为信息已经足够时，不要继续提问，只输出如下 JSON 草稿，不要输出任何其他内容：\n"
    '{"draft": {"title": "...", "goal": "...", "items": ['
    '{"title": "...", "subject": "...", "scheduled_date": "YYYY-MM-DD", '
    '"duration_minutes": 60, "order_index": 1}]}}\n'
    "5. 如果用户对已有草稿提出修改，按修改要求更新草稿并输出完整 JSON 草稿。\n"
    "6. 如果用户明确要求直接生成，立即输出草稿 JSON，不要再提问。"
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


def _is_fixed_question(content: str) -> bool:
    return any(content == question for _, question in FIELD_QUESTIONS)


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
    _save_context(session, {"__next_key": "major"})
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
    last_assistant = session.messages[-1].content if session.messages else ""
    if _is_fixed_question(last_assistant):
        next_key = context.get("__next_key") or _first_missing(context)
        if next_key and next_key != "done" and not context.get(next_key):
            context[next_key] = user_content.strip()
        next_missing = _first_missing(context)
        context["__next_key"] = next_missing or "done"
        _save_context(session, context)

    db.add(
        PlanChatMessage(
            session_id=session.id,
            role="user",
            content=user_content,
        )
    )
    db.flush()

    notes = "\n".join(
        f"- {message.content}" for message in session.messages if message.role == "user"
    )
    draft_hint = (
        f"\n当前草稿：{session.draft_json}\n请根据用户最新消息更新草稿。"
        if session.draft_json
        else ""
    )
    messages = [
        {
            "role": "user",
            "content": (
                f"用户到目前为止提供的信息：\n{notes}\n\n"
                f"用户最新消息：{user_content}\n"
                f"{draft_hint}\n\n"
                "请只输出你作为AI智学管家规划顾问的下一句话；"
                "如果信息已经足够，直接输出学习计划草稿 JSON，不要再提问。"
                "绝对不要替用户回答，不要补全用户的话。"
            ),
        }
    ]
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
    if not offline and user_turns >= 8:
        draft = _request_draft_with_ai(session)
        if draft is None:
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
        missing_key = context.get("__next_key") or _first_missing(context)
        if missing_key and missing_key != "done":
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


def _request_draft_with_ai(session: PlanChatSession) -> dict[str, Any] | None:
    notes = "\n".join(
        f"- {message.content}" for message in session.messages if message.role == "user"
    )
    messages = [
        {
            "role": "user",
            "content": (
                f"用户到目前为止提供的信息：\n{notes}\n\n"
                "信息已经足够，请不要再提问，直接输出完整的学习计划草稿 JSON。"
                "不要输出任何解释，不要替用户回答。"
            ),
        }
    ]
    text = AIModelGateway().chat(
        [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
        temperature=0.3,
    )
    data = extract_json(text)
    if (
        isinstance(data, dict)
        and isinstance(data.get("draft"), dict)
        and data["draft"].get("items")
    ):
        try:
            return _normalize_draft(data["draft"], "AI 对话学习计划")
        except ValueError:
            return None
    return None


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
