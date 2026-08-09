from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models import User, UserProfile
from app.schemas.user import TokenOut, UserLogin, UserRegister

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_for_user(user: User) -> TokenOut:
    return TokenOut(access_token=create_access_token(str(user.id)), user=user)


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(
    data: UserRegister,
    db: Annotated[Session, Depends(get_db)],
) -> TokenOut:
    exists = db.scalar(
        select(User).where(or_(User.email == data.email, User.username == data.username))
    )
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱或用户名已被注册")

    user = User(
        email=data.email,
        username=data.username,
        nickname=data.username,
        hashed_password=get_password_hash(data.password),
    )
    user.profile = UserProfile(daily_study_minutes=60)
    db.add(user)
    db.commit()
    db.refresh(user)
    user = db.scalar(
        select(User).options(selectinload(User.profile)).where(User.id == user.id)
    )
    return _token_for_user(user)


@router.post("/login", response_model=TokenOut)
def login(
    data: UserLogin,
    db: Annotated[Session, Depends(get_db)],
) -> TokenOut:
    user = db.scalar(
        select(User)
        .options(selectinload(User.profile))
        .where(or_(User.email == data.account, User.username == data.account))
    )
    if user is None or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")
    return _token_for_user(user)
