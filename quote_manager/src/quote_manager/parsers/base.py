"""Base parser interface and shared data structures."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class ParsedLineItem:
    """A single line item extracted from a quote."""
    item_number: int | None = None
    description: str = ""
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    notes: str | None = None


@dataclass
class ParsedQuote:
    """Structured quote data extracted from a source."""
    supplier_name: str | None = None
    supplier_email: str | None = None
    quote_number: str | None = None
    quote_date: str | None = None
    validity_date: str | None = None
    delivery_date: str | None = None
    delivery_days: int | None = None
    total_amount: Decimal | None = None
    currency: str = "JPY"
    payment_terms: str | None = None
    notes: str | None = None
    line_items: list[ParsedLineItem] = field(default_factory=list)
    raw_text: str = ""
    confidence: float = 0.0  # 0.0 to 1.0, how confident the parser is


class QuoteParser(ABC):
    """Abstract base class for quote parsers."""

    @abstractmethod
    def parse(self, source: bytes | str, metadata: dict | None = None) -> ParsedQuote | None:
        """Parse a source and extract quote data.

        Args:
            source: Raw content (text for email bodies, bytes for files).
            metadata: Additional context (sender email, subject, etc.).

        Returns:
            ParsedQuote if extraction succeeded, None if the source
            doesn't appear to contain quote data.
        """
        ...
