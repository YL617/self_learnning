from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import CoinTransaction, FocusSession, Pet, ShopItem, User
from app.schemas.focus import (
    CoinTransactionOut,
    FeedPetRequest,
    FocusCompleteRequest,
    FocusSessionOut,
    FocusSessionStart,
    FocusStatsOut,
    PetChatIn,
    PetChatOut,
    PetInteractionOut,
    PetMessageOut,
    PetOut,
    PetPlayStateOut,
    PetUpdate,
    ShopItemOut,
)
from app.services.engagement import (
    DAILY_FOCUS_COIN_CAP,
    award_coins,
    award_pet_exp,
    feed_pet,
    get_or_create_pet,
    record_checkin,
    record_daily_stat,
    refresh_pet_state,
    seed_shop_items,
    today_focus_coins,
)
from app.services.pet_ai import (
    PetAIServiceError,
    chat_with_pet,
    greet_pet,
    list_pet_messages,
    pat_pet,
    play_pet,
    revive_pet,
)
from app.services.pet_play import (
    PetPlayError,
    end_pet_play,
    get_play_state,
    start_pet_play,
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
    data: FocusCompleteRequest | None = None,
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
        verified = data.verified if data else True
        if verified:
            coins = max(1, session.duration_minutes // 5)
            remaining = DAILY_FOCUS_COIN_CAP - today_focus_coins(db, current_user.id)
            coins = max(0, min(coins, remaining))
            if coins > 0:
                award_coins(db, current_user.id, coins, "完成番茄钟")
                award_pet_exp(db, current_user.id, coins)
            record_daily_stat(
                db,
                current_user.id,
                focus_minutes=session.duration_minutes,
                coins=coins,
            )
            record_checkin(db, current_user)
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
    refresh_pet_state(pet)
    db.commit()
    db.refresh(pet)
    return pet


def _owned_pet(db: Session, user_id: int, pet_id: int) -> Pet:
    pet = db.scalar(
        select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id)
    )
    if pet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="宠物不存在")
    return pet


@pet_router.api_route("/{pet_id}", response_model=PetOut, methods=["PATCH", "PUT"])
def rename_pet(
    pet_id: int,
    data: PetUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Pet:
    pet = _owned_pet(db, current_user.id, pet_id)
    pet.name = data.name
    db.commit()
    db.refresh(pet)
    return pet


@pet_router.get("/{pet_id}/messages", response_model=list[PetMessageOut])
def list_pet_messages_endpoint(
    pet_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = 50,
) -> list[PetMessageOut]:
    pet = _owned_pet(db, current_user.id, pet_id)
    rows = list_pet_messages(db, pet, limit=min(max(limit, 1), 100))
    return list(reversed(rows))


@pet_router.post("/{pet_id}/greet", response_model=PetChatOut)
def greet_pet_endpoint(
    pet_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PetChatOut:
    pet = _owned_pet(db, current_user.id, pet_id)
    refresh_pet_state(pet)
    try:
        reply = greet_pet(db, pet)
    except PetAIServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    db.refresh(pet)
    messages = list(reversed(list_pet_messages(db, pet, 50)))
    return PetChatOut(reply=reply, pet=pet, messages=messages)


@pet_router.post("/{pet_id}/chat", response_model=PetChatOut)
def chat_with_pet_endpoint(
    pet_id: int,
    data: PetChatIn,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PetChatOut:
    pet = _owned_pet(db, current_user.id, pet_id)
    refresh_pet_state(pet)
    try:
        reply = chat_with_pet(db, pet, data.message)
    except PetAIServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    db.refresh(pet)
    messages = list(reversed(list_pet_messages(db, pet, 50)))
    return PetChatOut(reply=reply, pet=pet, messages=messages)


@pet_router.post("/{pet_id}/pat", response_model=PetInteractionOut)
def pat_pet_endpoint(
    pet_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PetInteractionOut:
    pet = _owned_pet(db, current_user.id, pet_id)
    refresh_pet_state(pet)
    try:
        reply = pat_pet(pet)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(pet)
    return PetInteractionOut(reply=reply, pet=pet)


@pet_router.post("/{pet_id}/play", response_model=PetInteractionOut)
def play_pet_endpoint(
    pet_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PetInteractionOut:
    pet = _owned_pet(db, current_user.id, pet_id)
    refresh_pet_state(pet)
    try:
        reply = play_pet(pet)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(pet)
    return PetInteractionOut(reply=reply, pet=pet)


@pet_router.post("/{pet_id}/revive", response_model=PetInteractionOut)
def revive_pet_endpoint(
    pet_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PetInteractionOut:
    pet = _owned_pet(db, current_user.id, pet_id)
    refresh_pet_state(pet)
    balance = sum(
        tx.amount
        for tx in db.scalars(
            select(CoinTransaction).where(CoinTransaction.user_id == current_user.id)
        ).all()
    )
    try:
        reply = revive_pet(db, pet, balance)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(pet)
    return PetInteractionOut(reply=reply, pet=pet)


@pet_router.post("/{pet_id}/play-out", response_model=PetPlayStateOut)
def start_pet_play_endpoint(
    pet_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PetPlayStateOut:
    pet = _owned_pet(db, current_user.id, pet_id)
    try:
        session, _ = start_pet_play(db, pet)
    except PetPlayError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(pet)
    return PetPlayStateOut(session=session, summary=None, pet=pet)


@pet_router.get("/{pet_id}/play-session", response_model=PetPlayStateOut)
def get_pet_play_state_endpoint(
    pet_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PetPlayStateOut:
    pet = _owned_pet(db, current_user.id, pet_id)
    session, summary, pet = get_play_state(db, pet)
    db.commit()
    db.refresh(pet)
    return PetPlayStateOut(session=session, summary=summary, pet=pet)


@pet_router.post("/{pet_id}/play-out/end", response_model=PetPlayStateOut)
def end_pet_play_endpoint(
    pet_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PetPlayStateOut:
    pet = _owned_pet(db, current_user.id, pet_id)
    try:
        session, summary = end_pet_play(db, pet)
    except PetPlayError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.refresh(pet)
    return PetPlayStateOut(session=session, summary=summary, pet=pet)


@pet_router.post("/{pet_id}/feed", response_model=PetOut)
def feed_pet_endpoint(
    pet_id: int,
    data: FeedPetRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Pet:
    pet = _owned_pet(db, current_user.id, pet_id)
    refresh_pet_state(pet)
    balance = sum(
        tx.amount
        for tx in db.scalars(
            select(CoinTransaction).where(CoinTransaction.user_id == current_user.id)
        ).all()
    )
    if balance < data.amount:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="智学币不足")
    award_coins(db, current_user.id, -data.amount, "喂食宠物")
    feed_pet(pet, data.amount)
    db.commit()
    db.refresh(pet)
    return pet


@pet_router.get("/shop", response_model=list[ShopItemOut])
def list_shop(
    db: Annotated[Session, Depends(get_db)],
) -> list[ShopItem]:
    seed_shop_items(db)
    return list(db.scalars(select(ShopItem).order_by(ShopItem.price)).all())


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
