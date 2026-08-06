from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models import (
    AnswerRecord,
    CoinTransaction,
    DailyStat,
    Document,
    FocusSession,
    KnowledgeChunk,
    Pet,
    PlanAdjustmentLog,
    PlanChatMessage,
    PlanChatSession,
    PlanItem,
    Question,
    StudyPlan,
    User,
    UserProfile,
    WrongBookItem,
)
from app.schemas.onboarding import OnboardingOut
from app.schemas.user import UserOut, UserProfileOut, UserProfileUpdate

router = APIRouter(prefix="/users", tags=["users"])
settings = get_settings()


def _delete_user_data(db: Session, user_id: int) -> None:
    plan_ids = select(StudyPlan.id).where(StudyPlan.user_id == user_id)
    db.execute(
        sa_delete(PlanAdjustmentLog).where(PlanAdjustmentLog.plan_id.in_(plan_ids))
    )
    db.execute(sa_delete(PlanItem).where(PlanItem.plan_id.in_(plan_ids)))
    db.execute(sa_delete(StudyPlan).where(StudyPlan.user_id == user_id))

    db.execute(sa_delete(AnswerRecord).where(AnswerRecord.user_id == user_id))
    db.execute(sa_delete(WrongBookItem).where(WrongBookItem.user_id == user_id))
    db.execute(sa_delete(Question).where(Question.user_id == user_id))

    document_ids = select(Document.id).where(Document.user_id == user_id)
    db.execute(
        sa_delete(KnowledgeChunk).where(KnowledgeChunk.document_id.in_(document_ids))
    )
    db.execute(sa_delete(Document).where(Document.user_id == user_id))

    db.execute(sa_delete(FocusSession).where(FocusSession.user_id == user_id))
    db.execute(sa_delete(Pet).where(Pet.user_id == user_id))
    db.execute(sa_delete(CoinTransaction).where(CoinTransaction.user_id == user_id))
    db.execute(sa_delete(DailyStat).where(DailyStat.user_id == user_id))

    session_ids = select(PlanChatSession.id).where(PlanChatSession.user_id == user_id)
    db.execute(
        sa_delete(PlanChatMessage).where(PlanChatMessage.session_id.in_(session_ids))
    )
    db.execute(sa_delete(PlanChatSession).where(PlanChatSession.user_id == user_id))

    user = db.get(User, user_id)
    if user is not None:
        db.delete(user)


@router.get("/me", response_model=UserOut)
def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    return db.scalar(
        select(User)
        .options(selectinload(User.profile))
        .where(User.id == current_user.id)
    )


@router.api_route("/me/profile", response_model=UserProfileOut, methods=["PATCH", "PUT"])
def update_profile(
    data: UserProfileUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> UserProfile:
    profile = current_user.profile
    if profile is None:
        profile = UserProfile(user_id=current_user.id, daily_study_minutes=60)
        db.add(profile)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return profile


@router.post("/me/membership/demo", response_model=UserOut)
def enable_demo_vip(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if settings.APP_ENV != "dev":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅演示环境可模拟开通 VIP",
        )
    current_user.membership_level = "vip"
    db.commit()
    return db.scalar(
        select(User)
        .options(selectinload(User.profile))
        .where(User.id == current_user.id)
    )


@router.get("/me/onboarding", response_model=OnboardingOut)
def get_onboarding(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> OnboardingOut:
    user = db.scalar(
        select(User)
        .options(selectinload(User.profile))
        .where(User.id == current_user.id)
    )
    return OnboardingOut(profile=user.profile)


@router.get("/me/export")
def export_user_data(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    plans = list(
        db.scalars(
            select(StudyPlan)
            .options(selectinload(StudyPlan.items))
            .where(StudyPlan.user_id == current_user.id)
        ).all()
    )
    questions = list(
        db.scalars(
            select(Question).where(Question.user_id == current_user.id)
        ).all()
    )
    wrong_book = list(
        db.scalars(
            select(WrongBookItem)
            .options(selectinload(WrongBookItem.question))
            .where(WrongBookItem.user_id == current_user.id)
        ).all()
    )
    sessions = list(
        db.scalars(
            select(PlanChatSession)
            .options(selectinload(PlanChatSession.messages))
            .where(PlanChatSession.user_id == current_user.id)
        ).all()
    )
    return jsonable_encoder({
        "user": {
            "email": current_user.email,
            "username": current_user.username,
            "membership_level": current_user.membership_level,
        },
        "profile": current_user.profile,
        "plans": plans,
        "questions": questions,
        "wrong_book": wrong_book,
        "focus_sessions": list(
            db.scalars(
                select(FocusSession).where(FocusSession.user_id == current_user.id)
            ).all()
        ),
        "pets": list(
            db.scalars(select(Pet).where(Pet.user_id == current_user.id)).all()
        ),
        "coin_transactions": list(
            db.scalars(
                select(CoinTransaction).where(CoinTransaction.user_id == current_user.id)
            ).all()
        ),
        "daily_stats": list(
            db.scalars(select(DailyStat).where(DailyStat.user_id == current_user.id)).all()
        ),
        "documents": list(
            db.scalars(select(Document).where(Document.user_id == current_user.id)).all()
        ),
        "plan_chat_sessions": sessions,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    })


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    _delete_user_data(db, current_user.id)
    db.commit()
