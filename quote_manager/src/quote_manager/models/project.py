"""Project (案件) model."""

from datetime import datetime

from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from quote_manager.models.base import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    gmail_query: Mapped[str | None] = mapped_column(String(500), nullable=True)
    slack_channel_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    slack_thread_ts: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    quotes: Mapped[list["Quote"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    email_records: Mapped[list["EmailRecord"]] = relationship(back_populates="project", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Project(id={self.id}, name='{self.name}', status='{self.status}')>"
