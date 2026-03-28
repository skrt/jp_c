"""Quote and LineItem models."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import String, Text, DateTime, Date, Numeric, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from quote_manager.models.base import Base


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    quote_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    quote_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    validity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivery_date: Mapped[str | None] = mapped_column(String(100), nullable=True)
    delivery_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="JPY")
    payment_terms: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(20))  # email_body, pdf, excel, slack
    source_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="quotes")
    supplier: Mapped["Supplier"] = relationship(back_populates="quotes")
    line_items: Mapped[list["LineItem"]] = relationship(
        back_populates="quote", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Quote(id={self.id}, supplier_id={self.supplier_id}, total={self.total_amount})>"


class LineItem(Base):
    __tablename__ = "line_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey("quotes.id"), nullable=False)
    item_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(15, 3), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    quote: Mapped["Quote"] = relationship(back_populates="line_items")

    def __repr__(self) -> str:
        return f"<LineItem(id={self.id}, desc='{self.description[:30]}', amount={self.amount})>"
