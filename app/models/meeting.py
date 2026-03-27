from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid


class Meeting(Base, TimestampMixin):
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    fc_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    contact_id: Mapped[str] = mapped_column(String(36), ForeignKey("contacts.id"), index=True)

    title: Mapped[str] = mapped_column(String(200))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scheduled_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(300))

    status: Mapped[str] = mapped_column(String(20), default="scheduled")  # scheduled | completed | cancelled
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    memo_submitted: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    contact = relationship("Contact", back_populates="meetings")
    interactions = relationship("Interaction", back_populates="meeting")
