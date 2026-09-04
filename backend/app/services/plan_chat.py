from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    PlanChatMessage,
    PlanChatSession,
    PlanItem,
    StudyPlan,
    UserProfile,
    WrongBookItem,
)
from app.services.ai_gateway import AIModelGateway, extract_json
from app.services.course_recommender import recommend_courses_for_plan
from app.services.study_planner import _normalize, generate_study_plan

SYSTEM_PROMPT = (
    "你是AI智学管家的学习规划顾问，语气专业、温和、自然。你的任务是帮助用户制定详细、可执行的学习计划。\n"
    "规则：\n"
    "1. 一次只问一个问题，不要一次问多个问题。\n"
    "2. 绝对不要替用户回答或替用户做决定，用户回答后你只做追问和整理。\n"
    "3. 结合用户已经提供的信息持续追问，避免重复提问；需要时追问考试或截止时间、每周可学习时段、当前基础、薄弱点、偏好方式、计划周期等。\n"
    "3.5 如果用户明确提到新方向、换方向、转行、重新规划、从零开始，"
    "以用户最新方向为准，忽略历史计划和历史目标，不要反复引导用户回到旧计划。\n"
    "4. 当你认为信息已经足够时，不要再提问，只输出如下 JSON，不要输出任何其他内容：\n"
    '{"type":"draft","draft":{"title":"...","goal":"...","items":[' 
    '{"title":"...","subject":"...","scheduled_date":"YYYY-MM-DD",'
    '"duration_minutes":60,"order_index":1}]}}\n'
    "5. 如果还需要了解信息，只输出如下 JSON，不要输出其他内容：\n"
    '{"type":"question","question":"...","field":"major|goal|daily_minutes|weeks|subjects|weak_points|learning_style|available_time_slots"}\n'
    "6. field 必须是上面列出的字段之一，且每次只输出一个问题。"
)

FIELD_QUESTIONS: list[tuple[str, str]] = [
    ("goal", "你这次想规划什么方向或达成什么目标？"),
    ("major", "你的专业和年级是什么？"),
    ("daily_minutes", "你每天大约能投入多少分钟学习？"),
    ("weeks", "你希望这个计划覆盖几周？"),
    ("subjects", "这段时间的重点科目有哪些？（用逗号分隔）"),
    ("weak_points", "你目前最薄弱的知识点或最想加强的部分是什么？"),
    ("learning_style", "你更喜欢哪种学习方式？看视频、做题、读教材还是混合？"),
]

FIELD_LABELS = {
    "major": "专业年级",
    "goal": "学习目标",
    "daily_minutes": "每日时长",
    "weeks": "计划周期",
    "subjects": "重点科目",
    "weak_points": "薄弱点",
    "learning_style": "学习方式",
    "available_time_slots": "可用时段",
}

DYNAMIC_FIELDS = [key for key, _ in FIELD_QUESTIONS] + ["available_time_slots"]


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


def _is_new_direction(content: str) -> bool:
    markers = (
        "新方向",
        "换方向",
        "换个方向",
        "重新规划",
        "重新制定",
        "重来",
        "从零开始",
        "转行",
        "不按原来的",
        "不是原来",
        "不想继续原来",
        "新的计划",
    )
    return any(marker in content for marker in markers)


def _known_labels(context: dict[str, str]) -> list[str]:
    labels: list[str] = []
    for key, _ in FIELD_QUESTIONS:
        if context.get(key):
            labels.append(FIELD_LABELS[key])
    if context.get("available_time_slots"):
        labels.append(FIELD_LABELS["available_time_slots"])
    return labels


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


def _build_profile_context(db: Session, user_id: int) -> dict[str, str]:
    profile = db.scalar(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    context: dict[str, str] = {}
    if profile is None:
        return context
    if profile.major:
        context["major"] = (
            f"{profile.major} {profile.grade}" if profile.grade else profile.major
        )
    elif profile.grade:
        context["grade"] = profile.grade
    if profile.goals:
        context["goal"] = profile.goals
    if profile.daily_study_minutes:
        context["daily_minutes"] = str(profile.daily_study_minutes)
    if profile.weak_subjects:
        context["weak_points"] = profile.weak_subjects
    elif profile.pain_point:
        context["weak_points"] = profile.pain_point
    if profile.learning_style:
        context["learning_style"] = profile.learning_style
    if profile.available_time_slots:
        context["available_time_slots"] = profile.available_time_slots
    return context


def _recent_plan_summary(db: Session, user_id: int, limit: int = 3) -> str:
    plans = db.scalars(
        select(StudyPlan)
        .where(StudyPlan.user_id == user_id)
        .order_by(StudyPlan.created_at.desc())
        .limit(limit)
    ).all()
    if not plans:
        return "无"
    lines: list[str] = []
    for plan in plans:
        done = sum(1 for item in plan.items if item.completed)
        lines.append(
            f"- {plan.title}（{plan.start_date} 至 {plan.end_date}，完成 {done}/{len(plan.items)}）"
        )
    return "\n".join(lines)


def _wrong_points(db: Session, user_id: int) -> str:
    rows = db.scalars(
        select(WrongBookItem)
        .where(
            WrongBookItem.user_id == user_id,
            WrongBookItem.mastered.is_(False),
            WrongBookItem.next_review_date <= date.today(),
        )
        .limit(6)
    ).all()
    points: list[str] = []
    for item in rows:
        point = item.question.knowledge_point if item.question else None
        if point and point not in points:
            points.append(point)
    return "、".join(points[:5]) or "无"


def _background_text(
    db: Session,
    session: PlanChatSession,
    context: dict[str, str],
) -> str:
    parts: list[str] = []
    for key, _ in FIELD_QUESTIONS:
        if context.get(key):
            parts.append(f"{FIELD_LABELS[key]}：{context[key]}")
    if context.get("available_time_slots"):
        parts.append(f"可用时段：{context['available_time_slots']}")
    if not parts:
        parts.append("用户尚未提供学情信息")
    history = (
        "用户明确要规划新方向，历史计划不参与参考"
        if context.get("new_direction") == "true"
        else _recent_plan_summary(db, session.user_id)
    )
    return (
        "\n".join(parts)
        + f"\n当前日期：{date.today().isoformat()}"
        + f"\n最近计划：{history}"
        + f"\n待复习错题知识点：{_wrong_points(db, session.user_id)}"
    )


def _field_lines(context: dict[str, str]) -> str:
    lines: list[str] = []
    for key, _ in FIELD_QUESTIONS:
        if context.get(key):
            lines.append(f"- {FIELD_LABELS[key]}：{context[key]}")
    if context.get("available_time_slots"):
        lines.append(f"- 可用时段：{context['available_time_slots']}")
    return "\n".join(lines) or "暂无"


def _refine_draft(
    db: Session,
    session: PlanChatSession,
    draft: dict[str, Any],
    max_attempts: int = 2,
) -> dict[str, Any] | None:
    context = _load_context(session)
    prompt = (
        "你是一位严格的学习计划审稿人。请检查并优化下面的计划草稿：\n"
        "1. 标题和目标是否具体明确；\n"
        "2. 任务是否可执行，是否覆盖重点科目和薄弱点；\n"
        "3. 日期是否覆盖整个计划周期；\n"
        "4. 每日学习负荷是否合理；\n"
        "5. 是否结合了用户背景和当前日期。\n\n"
        f"用户背景：\n{_background_text(db, session, context)}\n\n"
        f"当前草稿 JSON：\n{json.dumps(draft, ensure_ascii=False)}\n\n"
        '只输出优化后的完整草稿 JSON：{"title":"...","goal":"...","items":[...]}'
    )
    for _ in range(max_attempts):
        text = AIModelGateway().chat(
            [
                {
                    "role": "system",
                    "content": "你是学习计划质量审稿人，只输出 JSON，不要输出任何解释。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        data = extract_json(text)
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            try:
                return _normalize_draft(data, "AI 对话学习计划")
            except ValueError:
                continue
    return None


def _normalize_and_refine(
    db: Session,
    session: PlanChatSession,
    raw_draft: dict[str, Any],
) -> dict[str, Any] | None:
    try:
        draft = _normalize_draft(raw_draft, "AI 对话学习计划")
    except ValueError:
        return None
    refined = _refine_draft(db, session, draft)
    return refined or draft


def start_chat(db: Session, user_id: int) -> tuple[PlanChatSession, str, list[str]]:
    session = PlanChatSession(user_id=user_id, status="collecting")
    context = _build_profile_context(db, user_id)
    next_key = "goal"
    context["__next_key"] = next_key or "done"
    context["__awaiting_field"] = next_key or "done"
    _save_context(session, context)
    db.add(session)
    db.flush()
    first_question = _question_for("goal")
    db.add(
        PlanChatMessage(
            session_id=session.id,
            role="assistant",
            content=first_question,
        )
    )
    db.commit()
    db.refresh(session)
    return session, first_question, _known_labels(context)


def process_message(
    db: Session,
    session: PlanChatSession,
    user_content: str,
) -> dict[str, Any]:
    context = _load_context(session)
    user_text = user_content.strip()
    if _is_new_direction(user_text):
        context["new_direction"] = "true"
        for key in (
            "major",
            "grade",
            "subjects",
            "weak_points",
            "learning_style",
            "available_time_slots",
        ):
            context.pop(key, None)
    awaiting = context.get("__awaiting_field") or context.get("__next_key")
    if (
        awaiting
        and awaiting != "done"
        and awaiting in DYNAMIC_FIELDS
        and (awaiting == "goal" or not context.get(awaiting))
    ):
        context[awaiting] = user_text
    context["__next_key"] = _first_missing(context) or "done"
    context["__awaiting_field"] = "done"
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
                f"用户背景信息：\n{_background_text(db, session, context)}\n\n"
                f"用户已提供：\n{_field_lines(context)}\n\n"
                f"对话记录：\n{notes}\n\n"
                f"用户最新消息：{user_content}\n"
                f"{draft_hint}\n\n"
                "请只按系统格式输出 JSON：需要追问就输出 question，信息足够就输出 draft。"
                "绝对不要替用户回答，不要补全用户的话。"
            ),
        }
    ]
    text = AIModelGateway().chat(
        [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
        temperature=0.4,
    )
    data = extract_json(text)

    if isinstance(data, dict):
        if isinstance(data.get("draft"), dict) and data["draft"].get("items"):
            draft = _normalize_and_refine(db, session, data["draft"])
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
                return {
                    "reply": reply,
                    "status": session.status,
                    "draft": draft,
                    "known": _known_labels(context),
                }
        if data.get("type") == "question" and data.get("question"):
            field = data.get("field")
            if field not in DYNAMIC_FIELDS:
                field = context.get("__next_key") if context.get("__next_key") != "done" else None
            context["__awaiting_field"] = field or "done"
            _save_context(session, context)
            reply = str(data["question"])
            db.add(
                PlanChatMessage(
                    session_id=session.id,
                    role="assistant",
                    content=reply,
                )
            )
            db.commit()
            return {
                "reply": reply,
                "status": session.status,
                "draft": None,
                "known": _known_labels(context),
            }

    reply = text.strip()
    offline = not reply or "离线降级响应" in reply
    user_turns = sum(1 for message in session.messages if message.role == "user")
    if not offline and user_turns >= 8:
        draft = _request_draft_with_ai(db, session)
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
        return {
            "reply": reply,
            "status": session.status,
            "draft": draft,
            "known": _known_labels(context),
        }

    if offline:
        missing_key = context.get("__next_key") or _first_missing(context)
        if missing_key and missing_key != "done":
            context["__awaiting_field"] = missing_key
            _save_context(session, context)
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
            return {
                "reply": reply,
                "status": session.status,
                "draft": draft,
                "known": _known_labels(context),
            }

    context["__awaiting_field"] = context.get("__next_key") or "done"
    _save_context(session, context)
    db.add(
        PlanChatMessage(
            session_id=session.id,
            role="assistant",
            content=reply,
        )
    )
    db.commit()
    return {
        "reply": reply,
        "status": session.status,
        "draft": None,
        "known": _known_labels(context),
    }


def _request_draft_with_ai(
    db: Session, session: PlanChatSession
) -> dict[str, Any] | None:
    context = _load_context(session)
    notes = "\n".join(
        f"- {message.content}" for message in session.messages if message.role == "user"
    )
    messages = [
        {
            "role": "user",
            "content": (
                f"用户背景信息：\n{_background_text(db, session, context)}\n\n"
                f"用户已提供：\n{_field_lines(context)}\n\n"
                f"对话记录：\n{notes}\n\n"
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
    raw = data.get("draft") if isinstance(data, dict) else data
    if isinstance(raw, dict) and raw.get("items"):
        return _normalize_and_refine(db, session, raw)
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
    recommend_courses_for_plan(db, session.user_id, plan)
    return plan
