"""Parse quote data from email body text."""

import re
from decimal import Decimal, InvalidOperation

from quote_manager.parsers.base import QuoteParser, ParsedQuote, ParsedLineItem


# Price patterns (Japanese and international)
PRICE_PATTERNS = [
    re.compile(r"¥\s?([\d,]+)"),
    re.compile(r"([\d,]+)\s?円"),
    re.compile(r"JPY\s?([\d,]+)", re.IGNORECASE),
    re.compile(r"\$\s?([\d,.]+)"),
    re.compile(r"USD\s?([\d,.]+)", re.IGNORECASE),
]

# Total amount patterns
TOTAL_PATTERNS = [
    re.compile(r"(?:合計|総額|total|小計|税込|税抜)[\s:：]*¥?\s?([\d,]+)\s?円?", re.IGNORECASE),
    re.compile(r"(?:合計|総額|total)[\s:：]*\$?\s?([\d,.]+)", re.IGNORECASE),
]

# Quote number patterns
QUOTE_NUM_PATTERNS = [
    re.compile(r"(?:見積.*?(?:番号|No\.?)|Quote\s*#?|Quotation\s*#?)[\s:：]*(\S+)", re.IGNORECASE),
]

# Date patterns
DATE_PATTERNS = [
    re.compile(r"(\d{4}[/\-年]\d{1,2}[/\-月]\d{1,2}日?)"),
    re.compile(r"(\d{1,2}/\d{1,2}/\d{4})"),
]

# Delivery patterns
DELIVERY_PATTERNS = [
    re.compile(r"(?:納期|納入|delivery|lead\s*time)[\s:：]*(.+?)(?:\n|$)", re.IGNORECASE),
]

# Payment terms
PAYMENT_PATTERNS = [
    re.compile(r"(?:支払[い条件]*|payment\s*terms?)[\s:：]*(.+?)(?:\n|$)", re.IGNORECASE),
]

# Validity patterns
VALIDITY_PATTERNS = [
    re.compile(r"(?:有効期[限間]|valid(?:ity)?\s*(?:until|through|period)?)[\s:：]*(.+?)(?:\n|$)", re.IGNORECASE),
]

# Table-like row: item description, quantity, unit price, amount
TABLE_ROW_PATTERN = re.compile(
    r"(.+?)\s+"           # description
    r"(\d+(?:\.\d+)?)\s*" # quantity
    r"(?:個|本|台|式|set|pcs?|units?)?\s*"  # optional unit
    r"[×xX@]\s*"          # separator
    r"¥?([\d,]+)\s*"      # unit price
    r"(?:=|→|⇒)?\s*"     # optional separator
    r"¥?([\d,]+)",        # amount
    re.IGNORECASE,
)

# Simpler row pattern: description + price
SIMPLE_ROW_PATTERN = re.compile(
    r"^[・\-\*\d\.]+\s*(.+?)\s+¥?([\d,]+)\s?円?\s*$",
    re.MULTILINE,
)


def _parse_number(s: str) -> Decimal | None:
    """Parse a number string (with commas) to Decimal."""
    try:
        return Decimal(s.replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


class EmailBodyParser(QuoteParser):
    """Extract quote data from plain-text email bodies using regex patterns."""

    def parse(self, source: bytes | str, metadata: dict | None = None) -> ParsedQuote | None:
        if isinstance(source, bytes):
            source = source.decode("utf-8", errors="replace")

        if not source.strip():
            return None

        metadata = metadata or {}
        quote = ParsedQuote(
            supplier_email=metadata.get("sender_email"),
            supplier_name=metadata.get("sender_name"),
            raw_text=source,
        )

        # Extract quote number
        for pattern in QUOTE_NUM_PATTERNS:
            match = pattern.search(source)
            if match:
                quote.quote_number = match.group(1).strip()
                break

        # Extract dates
        dates = []
        for pattern in DATE_PATTERNS:
            dates.extend(pattern.findall(source))

        if dates:
            quote.quote_date = dates[0]

        # Extract validity
        for pattern in VALIDITY_PATTERNS:
            match = pattern.search(source)
            if match:
                quote.validity_date = match.group(1).strip()
                break

        # Extract delivery
        for pattern in DELIVERY_PATTERNS:
            match = pattern.search(source)
            if match:
                quote.delivery_date = match.group(1).strip()
                break

        # Extract payment terms
        for pattern in PAYMENT_PATTERNS:
            match = pattern.search(source)
            if match:
                quote.payment_terms = match.group(1).strip()
                break

        # Extract line items - try detailed table rows first
        for match in TABLE_ROW_PATTERN.finditer(source):
            desc, qty, unit_price, amount = match.groups()
            item = ParsedLineItem(
                description=desc.strip(),
                quantity=_parse_number(qty),
                unit_price=_parse_number(unit_price),
                amount=_parse_number(amount),
            )
            quote.line_items.append(item)

        # Fall back to simple rows if no table rows found
        if not quote.line_items:
            for match in SIMPLE_ROW_PATTERN.finditer(source):
                desc, amount = match.groups()
                item = ParsedLineItem(
                    description=desc.strip(),
                    amount=_parse_number(amount),
                )
                quote.line_items.append(item)

        # Extract total
        for pattern in TOTAL_PATTERNS:
            match = pattern.search(source)
            if match:
                quote.total_amount = _parse_number(match.group(1))
                break

        # If no total found but we have line items, sum them
        if quote.total_amount is None and quote.line_items:
            amounts = [li.amount for li in quote.line_items if li.amount is not None]
            if amounts:
                quote.total_amount = sum(amounts)

        # Determine confidence
        has_items = len(quote.line_items) > 0
        has_total = quote.total_amount is not None
        has_supplier = quote.supplier_name is not None

        if has_items and has_total:
            quote.confidence = 0.8
        elif has_items or has_total:
            quote.confidence = 0.5
        elif has_supplier:
            quote.confidence = 0.2
        else:
            quote.confidence = 0.1

        # Return None if we couldn't extract anything useful
        if not has_items and not has_total:
            return None

        return quote
