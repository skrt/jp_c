"""Supplier model."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from quote_manager.models.base import Base


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_person: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    quotes: Mapped[list["Quote"]] = relationship(back_populates="supplier")

    def __repr__(self) -> str:
        return f"<Supplier(id={self.id}, name='{self.name}')>"
