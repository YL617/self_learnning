from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_ai_access, require_membership
from app.core.database import get_db
from app.models import PlanChatMessage, PlanChatSession, User
from app.schemas.plan_chat import (
    PlanChatConfirmOut,
    PlanChatMessageOut,
    PlanChatReply,
    PlanChatSendIn,
    PlanChatStartOut,
)
from app.services.content_filter import validate_text
from app.services.plan_chat import confirm_chat, process_message, start_chat

router = APIRouter(prefix="/plans/chat", tags=["plans-chat"])


def _get_own_session(db: Session, user_id: int, session_id: int) -> PlanChatSession:
    session = db.scalar(
        select(PlanChatSession)
        .options(selectinload(PlanChatSession.messages))
        .where(
            PlanChatSession.id == session_id,
            PlanChatSession.user_id == user_id,
        )
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话会话不存在")
    return session


@router.post("", response_model=PlanChatStartOut, status_code=status.HTTP_201_CREATED)
def create_chat(
    current_user: Annotated[User, Depends(require_membership("advanced"))],
    db: Annotated[Session, Depends(get_db)],
) -> PlanChatStartOut:
    session, reply, known = start_chat(db, current_user.id)
    return PlanChatStartOut(
        session_id=session.id,
        reply=reply,
        status=session.status,
        known=known,
    )


@router.get("/{session_id}/messages", response_model=list[PlanChatMessageOut])
def list_messages(
    session_id: int,
    current_user: Annotated[User, Depends(require_membership("advanced"))],
    db: Annotated[Session, Depends(get_db)],
) -> list[PlanChatMessage]:
    session = _get_own_session(db, current_user.id, session_id)
    return session.messages


@router.post("/{session_id}/messages", response_model=PlanChatReply)
def send_message(
    session_id: int,
    data: PlanChatSendIn,
    current_user: Annotated[User, Depends(require_ai_access("advanced"))],
    db: Annotated[Session, Depends(get_db)],
) -> PlanChatReply:
    try:
        validate_text(data.content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session = _get_own_session(db, current_user.id, session_id)
    if session.status == "confirmed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="会话已确认完成")
    result = process_message(db, session, data.content)
    return PlanChatReply(
        session_id=session.id,
        reply=result["reply"],
        status=result["status"],
        draft=result.get("draft"),
        known=result.get("known", []),
    )


@router.post("/{session_id}/confirm", response_model=PlanChatConfirmOut)
def confirm_plan(
    session_id: int,
    current_user: Annotated[User, Depends(require_membership("advanced"))],
    db: Annotated[Session, Depends(get_db)],
) -> PlanChatConfirmOut:
    session = _get_own_session(db, current_user.id, session_id)
    try:
        plan = confirm_chat(db, session)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return PlanChatConfirmOut(plan_id=plan.id, message="学习计划已生成")
