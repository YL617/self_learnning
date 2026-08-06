from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models import User, UserProfile
from app.schemas.onboarding import OnboardingOut
from app.schemas.user import UserOut, UserProfileOut, UserProfileUpdate

router = APIRouter(prefix="/users", tags=["users"])
settings = get_settings()


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
