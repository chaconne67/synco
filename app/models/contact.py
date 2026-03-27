from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid


class Contact(Base, TimestampMixin):
    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    fc_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    ceo_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))

    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20))
    company_name: Mapped[str | None] = mapped_column(String(200))
    industry: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    revenue_range: Mapped[str | None] = mapped_column(String(50))
    employee_count: Mapped[str | None] = mapped_column(String(50))
    memo: Mapped[str | None] = mapped_column(Text)

    last_interaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    fc = relationship("User", back_populates="contacts", foreign_keys=[fc_id])
    meetings = relationship("Meeting", back_populates="contact")
    interactions = relationship("Interaction", back_populates="contact")
    briefs = relationship("Brief", back_populates="contact")
