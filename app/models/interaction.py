from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid


class Interaction(Base, TimestampMixin):
    __tablename__ = "interactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    fc_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    contact_id: Mapped[str] = mapped_column(String(36), ForeignKey("contacts.id"), index=True)
    meeting_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("meetings.id"))

    type: Mapped[str] = mapped_column(String(20))  # call | meeting | message | memo
    summary: Mapped[str | None] = mapped_column(Text)
    sentiment: Mapped[str | None] = mapped_column(String(20))  # positive | neutral | negative

    # Relationships
    contact = relationship("Contact", back_populates="interactions")
    meeting = relationship("Meeting", back_populates="interactions")
