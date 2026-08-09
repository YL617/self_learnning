from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CoinTransaction, Pet, PetPlaySession
from app.services.engagement import award_coins, refresh_pet_state

PLAY_COST = 20
PLAY_DURATION_MINUTES = 15
PLAY_MOOD_GAIN = 15
PLAY_EXP_GAIN = 20
PLAY_HUNGER_LOSS = 15
DAILY_PLAY_LIMIT = 5
MIN_HUNGER_TO_PLAY = 20


class PetPlayError(ValueError):
    """出门玩规则校验失败。"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _today() -> date:
    return date.today()


def _active_session(db: Session, pet: Pet) -> PetPlaySession | None:
    return db.scalar(
        select(PetPlaySession)
        .where(PetPlaySession.pet_id == pet.id, PetPlaySession.status == "active")
        .order_by(PetPlaySession.id.desc())
        .limit(1)
    )


def _reset_daily_count(pet: Pet) -> None:
    today = _today()
    if pet.play_date != today:
        pet.play_date = today
        pet.play_count_today = 0


def _balance(db: Session, pet: Pet) -> int:
    transactions = db.scalars(
        select(CoinTransaction).where(CoinTransaction.user_id == pet.user_id)
    ).all()
    return sum(tx.amount for tx in transactions)


def _grant_play_rewards(pet: Pet, mood_gain: int, exp_gain: int, hunger_loss: int) -> None:
    pet.mood = min(100, pet.mood + mood_gain)
    pet.exp += exp_gain
    while pet.exp >= pet.level * 100:
        pet.exp -= pet.level * 100
        pet.level += 1
    pet.hunger = max(0, pet.hunger - hunger_loss)


def start_pet_play(db: Session, pet: Pet) -> tuple[PetPlaySession, Pet]:
    refresh_pet_state(pet)
    now = _utcnow()
    if pet.runaway:
        raise PetPlayError("宠物离家出走了，请先使用寻回卷轴")

    active = _active_session(db, pet)
    playing_until = _as_aware(pet.playing_until)
    if active is not None:
        if playing_until is not None and playing_until <= now:
            end_pet_play(db, pet, force_complete=True)
        else:
            raise PetPlayError("宠物正在出门玩，请等它回来")
    elif playing_until is not None and playing_until > now:
        raise PetPlayError("宠物正在出门玩，请等它回来")

    if pet.hunger < MIN_HUNGER_TO_PLAY:
        raise PetPlayError("宠物太饿了，先喂点吃的再出门")
    balance = _balance(db, pet)
    if balance < PLAY_COST:
        raise PetPlayError(f"智学币不足，出门玩需要 {PLAY_COST} 智学币")

    _reset_daily_count(pet)
    if pet.play_count_today >= DAILY_PLAY_LIMIT:
        raise PetPlayError("今天出门玩的次数已经用完，明天再来吧")

    award_coins(db, pet.user_id, -PLAY_COST, "出门玩")
    session = PetPlaySession(
        pet_id=pet.id,
        status="active",
        started_at=now.replace(tzinfo=None),
        duration_minutes=PLAY_DURATION_MINUTES,
        coin_cost=PLAY_COST,
        mood_gain=PLAY_MOOD_GAIN,
        exp_gain=PLAY_EXP_GAIN,
        hunger_loss=PLAY_HUNGER_LOSS,
    )
    pet.play_count_today += 1
    pet.playing_until = (now + timedelta(minutes=PLAY_DURATION_MINUTES)).replace(
        tzinfo=None
    )
    db.add(session)
    db.flush()
    return session, pet


def get_play_state(
    db: Session,
    pet: Pet,
) -> tuple[PetPlaySession | None, dict[str, Any] | None, Pet]:
    refresh_pet_state(pet)
    session = _active_session(db, pet)
    playing_until = _as_aware(pet.playing_until)
    if session is not None and playing_until is not None and playing_until <= _utcnow():
        _, summary = end_pet_play(db, pet, force_complete=True)
        return None, summary, pet
    if session is None and pet.playing_until is not None:
        pet.playing_until = None
    return session, None, pet


def end_pet_play(
    db: Session,
    pet: Pet,
    *,
    force_complete: bool = False,
) -> tuple[PetPlaySession, dict[str, Any]]:
    session = _active_session(db, pet)
    if session is None:
        last = db.scalar(
            select(PetPlaySession)
            .where(PetPlaySession.pet_id == pet.id)
            .order_by(PetPlaySession.id.desc())
            .limit(1)
        )
        if last is not None:
            return last, {
                "elapsed_minutes": 0,
                "mood_gain": 0,
                "exp_gain": 0,
                "hunger_loss": 0,
                "coins_spent": last.coin_cost,
                "message": "这次出门玩已经结束啦",
            }
        raise PetPlayError("没有正在进行的出门玩会话")

    now = _utcnow()
    started = _as_aware(session.started_at) or now
    playing_until = _as_aware(pet.playing_until) or (
        started + timedelta(minutes=session.duration_minutes)
    )
    full = force_complete or (playing_until is not None and now >= playing_until)
    if full:
        elapsed = session.duration_minutes
    else:
        raw_minutes = int(max(0, (now - started).total_seconds() // 60))
        elapsed = max(1, min(raw_minutes, session.duration_minutes))

    ratio = elapsed / session.duration_minutes
    mood_gain = int(session.mood_gain * ratio)
    exp_gain = int(session.exp_gain * ratio)
    hunger_loss = int(session.hunger_loss * ratio)
    _grant_play_rewards(pet, mood_gain, exp_gain, hunger_loss)

    session.status = "completed"
    session.ended_at = now.replace(tzinfo=None)
    pet.playing_until = None
    db.commit()
    db.refresh(pet)
    return session, {
        "elapsed_minutes": elapsed,
        "mood_gain": mood_gain,
        "exp_gain": exp_gain,
        "hunger_loss": hunger_loss,
        "coins_spent": session.coin_cost,
        "message": "小智玩够时间，自己回来啦" if full else "小智提前回来了",
    }
