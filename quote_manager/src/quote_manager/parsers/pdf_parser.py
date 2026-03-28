"""Parse quote data from PDF files."""

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber

from quote_manager.parsers.base import QuoteParser, ParsedQuote, ParsedLineItem


# Header keywords to identify table columns (Japanese + English)
HEADER_KEYWORDS = {
    "description": ["品名", "品目", "名称", "摘要", "内容", "item", "description", "product"],
    "quantity": ["数量", "qty", "quantity", "数"],
    "unit": ["単位", "unit"],
    "unit_price": ["単価", "unit price", "price"],
    "amount": ["金額", "amount", "合計", "小計", "計"],
}

TOTAL_KEYWORDS = ["合計", "総額", "total", "小計", "税込合計", "税抜合計", "御見積金額"]
QUOTE_NUM_KEYWORDS = ["見積番号", "見積No", "Quote No", "Quotation No", "No."]
DATE_KEYWORDS = ["見積日", "日付", "Date"]


def _parse_number(s: str) -> Decimal | None:
    if not s:
        return None
    cleaned = re.sub(r"[¥￥$,\s円]", "", str(s))
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _find_column_mapping(header_row: list[str]) -> dict[str, int]:
    """Map column indices to field names based on header keywords."""
    mapping = {}
    for idx, cell in enumerate(header_row):
        if cell is None:
            continue
        cell_lower = str(cell).lower().strip()
        for field_name, keywords in HEADER_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in cell_lower:
                    mapping[field_name] = idx
                    break
    return mapping


def _extract_text_metadata(full_text: str) -> dict:
    """Extract metadata (quote number, dates, total) from full PDF text."""
    metadata = {}

    # Quote number
    for kw in QUOTE_NUM_KEYWORDS:
        pattern = re.compile(rf"{re.escape(kw)}[\s:：]*(\S+)", re.IGNORECASE)
        match = pattern.search(full_text)
        if match:
            metadata["quote_number"] = match.group(1).strip()
            break

    # Dates
    date_pattern = re.compile(r"(\d{4}[/\-年]\d{1,2}[/\-月]\d{1,2}日?)")
    dates = date_pattern.findall(full_text)
    if dates:
        metadata["quote_date"] = dates[0]

    # Total
    for kw in TOTAL_KEYWORDS:
        pattern = re.compile(
            rf"{re.escape(kw)}[\s:：]*[¥￥]?\s?([\d,]+)", re.IGNORECASE
        )
        match = pattern.search(full_text)
        if match:
            metadata["total_amount"] = _parse_number(match.group(1))
            break

    # Delivery
    delivery_pattern = re.compile(r"(?:納期|納入日|delivery)[\s:：]*(.+?)(?:\n|$)", re.IGNORECASE)
    match = delivery_pattern.search(full_text)
    if match:
        metadata["delivery_date"] = match.group(1).strip()

    # Payment terms
    payment_pattern = re.compile(r"(?:支払条件|payment)[\s:：]*(.+?)(?:\n|$)", re.IGNORECASE)
    match = payment_pattern.search(full_text)
    if match:
        metadata["payment_terms"] = match.group(1).strip()

    # Validity
    validity_pattern = re.compile(r"(?:有効期限|valid)[\s:：]*(.+?)(?:\n|$)", re.IGNORECASE)
    match = validity_pattern.search(full_text)
    if match:
        metadata["validity_date"] = match.group(1).strip()

    return metadata


class PdfParser(QuoteParser):
    """Extract quote data from PDF files using pdfplumber."""

    def parse(self, source: bytes | str, metadata: dict | None = None) -> ParsedQuote | None:
        """Parse a PDF file.

        Args:
            source: File path (str) or PDF bytes.
            metadata: Additional context.
        """
        metadata = metadata or {}

        if isinstance(source, str):
            file_path = Path(source)
            if not file_path.exists():
                return None
            pdf = pdfplumber.open(file_path)
        else:
            import io
            pdf = pdfplumber.open(io.BytesIO(source))

        try:
            # Extract all text for metadata
            full_text = ""
            all_tables = []

            for page in pdf.pages:
                page_text = page.extract_text() or ""
                full_text += page_text + "\n"

                tables = page.extract_tables()
                all_tables.extend(tables)

            text_meta = _extract_text_metadata(full_text)

            quote = ParsedQuote(
                supplier_name=metadata.get("sender_name"),
                supplier_email=metadata.get("sender_email"),
                quote_number=text_meta.get("quote_number"),
                quote_date=text_meta.get("quote_date"),
                validity_date=text_meta.get("validity_date"),
                delivery_date=text_meta.get("delivery_date"),
                total_amount=text_meta.get("total_amount"),
                payment_terms=text_meta.get("payment_terms"),
                raw_text=full_text,
            )

            # Try to parse tables
            for table in all_tables:
                if not table or len(table) < 2:
                    continue

                # First row is likely the header
                col_map = _find_column_mapping(table[0])

                if "description" not in col_map:
                    # Try second row as header
                    if len(table) > 2:
                        col_map = _find_column_mapping(table[1])
                        data_rows = table[2:]
                    else:
                        continue
                else:
                    data_rows = table[1:]

                if "description" not in col_map:
                    continue

                for i, row in enumerate(data_rows):
                    if not row or all(cell is None or str(cell).strip() == "" for cell in row):
                        continue

                    desc_idx = col_map["description"]
                    desc = str(row[desc_idx]).strip() if desc_idx < len(row) and row[desc_idx] else ""

                    if not desc or any(kw in desc.lower() for kw in ["合計", "total", "小計"]):
                        continue

                    item = ParsedLineItem(
                        item_number=i + 1,
                        description=desc,
                    )

                    if "quantity" in col_map and col_map["quantity"] < len(row):
                        item.quantity = _parse_number(str(row[col_map["quantity"]] or ""))

                    if "unit" in col_map and col_map["unit"] < len(row):
                        item.unit = str(row[col_map["unit"]] or "").strip() or None

                    if "unit_price" in col_map and col_map["unit_price"] < len(row):
                        item.unit_price = _parse_number(str(row[col_map["unit_price"]] or ""))

                    if "amount" in col_map and col_map["amount"] < len(row):
                        item.amount = _parse_number(str(row[col_map["amount"]] or ""))

                    quote.line_items.append(item)

                if quote.line_items:
                    break  # Use the first table that yields items

            # Calculate confidence
            if quote.line_items and quote.total_amount:
                quote.confidence = 0.9
            elif quote.line_items:
                quote.confidence = 0.7
            elif quote.total_amount:
                quote.confidence = 0.5
            else:
                quote.confidence = 0.2

            if not quote.line_items and not quote.total_amount:
                return None

            return quote

        finally:
            pdf.close()
