from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PlanChatSession(Base):
    __tablename__ = "plan_chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="collecting")
    collected_context: Mapped[str] = mapped_column(Text, default="{}")
    draft_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["PlanChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="PlanChatMessage.id",
    )


class PlanChatMessage(Base):
    __tablename__ = "plan_chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("plan_chat_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    session: Mapped[PlanChatSession] = relationship(back_populates="messages")
