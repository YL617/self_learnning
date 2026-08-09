from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AiProviderSnapshot(Base):
    __tablename__ = "ai_provider_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    total_balance: Mapped[str] = mapped_column(String(64), default="0")
    granted_balance: Mapped[str] = mapped_column(String(64), default="0")
    topped_up_balance: Mapped[str] = mapped_column(String(64), default="0")
    is_available: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AiUsageRecord(Base):
    __tablename__ = "ai_usage_records"
    __table_args__ = (
        UniqueConstraint("provider", "usage_date", name="uq_ai_usage_provider_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    usage_date: Mapped[date] = mapped_column(Date)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float] = mapped_column(Float, default=0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
