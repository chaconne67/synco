from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class Match(Base, TimestampMixin):
    __tablename__ = "matches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    contact_a_id: Mapped[str] = mapped_column(String(36), ForeignKey("contacts.id"), index=True)
    contact_b_id: Mapped[str] = mapped_column(String(36), ForeignKey("contacts.id"), index=True)
    fc_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)

    score: Mapped[float] = mapped_column(Float, default=0)
    industry_fit: Mapped[float] = mapped_column(Float, default=0)
    region_proximity: Mapped[float] = mapped_column(Float, default=0)
    size_balance: Mapped[float] = mapped_column(Float, default=0)

    synergy_description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="proposed")  # proposed | viewed | accepted | rejected
