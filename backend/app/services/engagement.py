from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CoinTransaction, DailyStat, Pet


def get_or_create_pet(db: Session, user_id: int) -> Pet:
    pet = db.scalar(select(Pet).where(Pet.user_id == user_id))
    if pet is None:
        pet = Pet(user_id=user_id, name="小智")
        db.add(pet)
        db.flush()
    return pet


def add_pet_exp(pet: Pet, exp: int) -> Pet:
    pet.exp += exp
    while pet.exp >= pet.level * 100:
        pet.exp -= pet.level * 100
        pet.level += 1
    pet.mood = min(100, pet.mood + 2)
    return pet


def award_coins(db: Session, user_id: int, amount: int, reason: str) -> CoinTransaction:
    transaction = CoinTransaction(user_id=user_id, amount=amount, reason=reason)
    db.add(transaction)
    db.flush()
    return transaction


def award_pet_exp(db: Session, user_id: int, exp: int) -> Pet:
    pet = get_or_create_pet(db, user_id)
    return add_pet_exp(pet, exp)


def record_daily_stat(
    db: Session,
    user_id: int,
    *,
    focus_minutes: int = 0,
    answered: int = 0,
    correct: int = 0,
    coins: int = 0,
) -> DailyStat:
    today = date.today()
    stat = db.scalar(
        select(DailyStat).where(DailyStat.user_id == user_id, DailyStat.stat_date == today)
    )
    if stat is None:
        stat = DailyStat(user_id=user_id, stat_date=today)
        db.add(stat)
        db.flush()
    stat.focus_minutes += focus_minutes
    stat.answered_count += answered
    stat.correct_count += correct
    stat.coin_earned += coins
    return stat
