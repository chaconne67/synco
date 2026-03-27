from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, generate_uuid


class Brief(Base):
    __tablename__ = "briefs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    contact_id: Mapped[str] = mapped_column(String(36), ForeignKey("contacts.id"), index=True)
    fc_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)

    company_analysis: Mapped[str | None] = mapped_column(Text)
    action_suggestion: Mapped[str | None] = mapped_column(Text)
    insights: Mapped[dict | None] = mapped_column(JSONB)

    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Relationships
    contact = relationship("Contact", back_populates="briefs")
