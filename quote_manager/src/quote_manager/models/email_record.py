"""Email/Message record model for deduplication tracking."""

from datetime import datetime

from sqlalchemy import String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from quote_manager.models.base import Base


class EmailRecord(Base):
    __tablename__ = "email_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # "gmail" or "slack"
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sender: Mapped[str | None] = mapped_column(String(255), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    attachment_paths: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list

    # Relationships
    project: Mapped["Project | None"] = relationship(back_populates="email_records")

    def __repr__(self) -> str:
        return f"<EmailRecord(id={self.id}, source='{self.source}', sender='{self.sender}')>"
