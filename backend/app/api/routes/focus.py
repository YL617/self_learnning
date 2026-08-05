from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import CoinTransaction, FocusSession, Pet, User
from app.schemas.focus import (
    CoinTransactionOut,
    FeedPetRequest,
    FocusSessionOut,
    FocusSessionStart,
    FocusStatsOut,
    PetOut,
    PetUpdate,
)
from app.services.engagement import (
    add_pet_exp,
    award_coins,
    award_pet_exp,
    get_or_create_pet,
    record_daily_stat,
)

router = APIRouter(prefix="/focus", tags=["focus"])
pet_router = APIRouter(prefix="/pets", tags=["pets"])
coin_router = APIRouter(prefix="/coins", tags=["coins"])


@router.post("/sessions", response_model=FocusSessionOut, status_code=status.HTTP_201_CREATED)
def start_focus_session(
    data: FocusSessionStart,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FocusSession:
    session = FocusSession(
        user_id=current_user.id,
        task_label=data.task_label,
        duration_minutes=data.duration_minutes,
        started_at=datetime.now(timezone.utc),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.api_route(
    "/sessions/{session_id}/complete",
    response_model=FocusSessionOut,
    methods=["PATCH", "PUT"],
)
def complete_focus_session(
    session_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FocusSession:
    session = db.scalar(
        select(FocusSession).where(
            FocusSession.id == session_id,
            FocusSession.user_id == current_user.id,
        )
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="专注记录不存在")
    if not session.completed:
        session.completed = True
        session.ended_at = datetime.now(timezone.utc)
        coins = max(1, session.duration_minutes // 5)
        award_coins(db, current_user.id, coins, "完成番茄钟")
        award_pet_exp(db, current_user.id, coins)
        record_daily_stat(
            db,
            current_user.id,
            focus_minutes=session.duration_minutes,
            coins=coins,
        )
    db.commit()
    db.refresh(session)
    return session


@router.get("/stats", response_model=FocusStatsOut)
def focus_stats(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FocusStatsOut:
    sessions = db.scalars(
        select(FocusSession).where(
            FocusSession.user_id == current_user.id,
            FocusSession.completed.is_(True),
        )
    ).all()
    today = date.today()
    return FocusStatsOut(
        total_minutes=sum(s.duration_minutes for s in sessions),
        session_count=len(sessions),
        today_minutes=sum(
            s.duration_minutes
            for s in sessions
            if s.ended_at is not None and s.ended_at.date() == today
        ),
    )


@pet_router.get("", response_model=PetOut)
def get_pet(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Pet:
    pet = get_or_create_pet(db, current_user.id)
    db.commit()
    db.refresh(pet)
    return pet


@pet_router.api_route("/{pet_id}", response_model=PetOut, methods=["PATCH", "PUT"])
def rename_pet(
    pet_id: int,
    data: PetUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Pet:
    pet = db.scalar(
        select(Pet).where(Pet.id == pet_id, Pet.user_id == current_user.id)
    )
    if pet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="宠物不存在")
    pet.name = data.name
    db.commit()
    db.refresh(pet)
    return pet


@pet_router.post("/{pet_id}/feed", response_model=PetOut)
def feed_pet(
    pet_id: int,
    data: FeedPetRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Pet:
    pet = db.scalar(
        select(Pet).where(Pet.id == pet_id, Pet.user_id == current_user.id)
    )
    if pet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="宠物不存在")
    balance = sum(
        tx.amount
        for tx in db.scalars(
            select(CoinTransaction).where(CoinTransaction.user_id == current_user.id)
        ).all()
    )
    if balance < data.amount:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="智学币不足")
    award_coins(db, current_user.id, -data.amount, "喂食宠物")
    add_pet_exp(pet, data.amount)
    db.commit()
    db.refresh(pet)
    return pet


@coin_router.get("/transactions", response_model=list[CoinTransactionOut])
def list_transactions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[CoinTransaction]:
    return list(
        db.scalars(
            select(CoinTransaction)
            .where(CoinTransaction.user_id == current_user.id)
            .order_by(CoinTransaction.created_at.desc())
            .limit(50)
        ).all()
    )
