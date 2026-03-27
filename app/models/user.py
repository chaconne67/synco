from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    kakao_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str | None] = mapped_column(String(10))  # 'fc' | 'ceo' | None (미선택)
    profile_image: Mapped[str | None] = mapped_column(Text)

    # FC 전용
    ga_name: Mapped[str | None] = mapped_column(String(200))

    # CEO 전용
    company_name: Mapped[str | None] = mapped_column(String(200))
    industry: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    revenue_range: Mapped[str | None] = mapped_column(String(50))
    employee_count: Mapped[str | None] = mapped_column(String(50))

    # Push notification
    push_subscription: Mapped[str | None] = mapped_column(Text)

    # Relationships
    contacts = relationship("Contact", back_populates="fc", foreign_keys="Contact.fc_id")
