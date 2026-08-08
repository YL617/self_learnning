from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CoinTransaction, DailyStat, Pet, ShopItem, User

DAILY_FOCUS_COIN_CAP = 40


def refresh_pet_state(pet: Pet) -> Pet:
    now = datetime.now(timezone.utc)
    if pet.hunger_updated_at is None:
        pet.hunger_updated_at = now
        return pet
    if pet.hunger_updated_at.tzinfo is None:
        pet.hunger_updated_at = pet.hunger_updated_at.replace(tzinfo=timezone.utc)
    elapsed_hours = max(0, (now - pet.hunger_updated_at).total_seconds() / 3600)
    local_hour = (now + timedelta(hours=8)).hour
    decay_per_hour = 4 if local_hour >= 22 or local_hour < 6 else 2
    pet.hunger = max(0, pet.hunger - int(elapsed_hours * decay_per_hour))
    pet.hunger_updated_at = now
    if pet.hunger <= 0 and not pet.runaway:
        pet.runaway = True
    return pet


def feed_pet(pet: Pet, amount: int) -> Pet:
    refresh_pet_state(pet)
    if amount >= 50:
        pet.hunger = min(100, pet.hunger + 45)
        pet.exp += 50
        pet.mood = min(100, pet.mood + 12)
    else:
        pet.hunger = min(100, pet.hunger + 25)
        pet.exp += 10
        pet.mood = min(100, pet.mood + 5)
    pet.runaway = False
    pet.last_fed_at = datetime.now(timezone.utc)
    return add_pet_exp(pet, 0)


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
    refresh_pet_state(pet)
    return add_pet_exp(pet, exp)


def record_checkin(db: Session, user: User) -> int:
    today = date.today()
    if user.last_checkin_date == today:
        return 0
    if user.last_checkin_date == today - timedelta(days=1):
        user.checkin_streak += 1
    else:
        user.checkin_streak = 1
    user.last_checkin_date = today
    if user.checkin_streak == 3:
        award_coins(db, user.id, 50, "连续打卡 3 天")
        return 50
    if user.checkin_streak == 7:
        award_coins(db, user.id, 200, "连续打卡 7 天")
        return 200
    return 0


def today_focus_coins(db: Session, user_id: int) -> int:
    today = date.today()
    rows = db.scalars(
        select(CoinTransaction).where(
            CoinTransaction.user_id == user_id,
            CoinTransaction.reason == "完成番茄钟",
        )
    ).all()
    return sum(
        tx.amount
        for tx in rows
        if tx.created_at is not None
        and tx.created_at.date() == today
    )


def seed_shop_items(db: Session) -> None:
    if db.scalar(select(ShopItem).limit(1)) is not None:
        return
    db.add_all(
        [
            ShopItem(name="普通饲料", price=10, effect_type="feed", description="恢复饱食度并少量增加经验"),
            ShopItem(name="高级营养膏", price=50, effect_type="nutrition", description="大幅恢复饱食度并增加较多经验"),
            ShopItem(name="请假条", price=100, effect_type="leave", description="允许一天不打卡且宠物不掉状态"),
            ShopItem(name="寻回卷轴", price=200, effect_type="revive", description="找回离家出走的宠物"),
        ]
    )
    db.commit()


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
