"""Parse quote data from Excel files."""

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import load_workbook

from quote_manager.parsers.base import QuoteParser, ParsedQuote, ParsedLineItem


# Header keywords (same as PDF parser)
HEADER_KEYWORDS = {
    "description": ["品名", "品目", "名称", "摘要", "内容", "商品", "item", "description", "product"],
    "quantity": ["数量", "qty", "quantity", "数"],
    "unit": ["単位", "unit"],
    "unit_price": ["単価", "unit price", "price"],
    "amount": ["金額", "amount", "計"],
}

METADATA_KEYWORDS = {
    "quote_number": ["見積番号", "見積No", "Quote No", "Quotation No"],
    "quote_date": ["見積日", "日付", "Date"],
    "delivery_date": ["納期", "納入", "delivery", "lead time"],
    "payment_terms": ["支払条件", "支払い条件", "payment"],
    "validity_date": ["有効期限", "valid"],
    "total_amount": ["合計", "総額", "total", "御見積金額"],
}


def _parse_number(val) -> Decimal | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return Decimal(str(val))
    s = re.sub(r"[¥￥$,\s円]", "", str(val))
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _cell_matches_keywords(cell_value, keywords: list[str]) -> bool:
    if cell_value is None:
        return False
    cell_str = str(cell_value).lower().strip()
    return any(kw.lower() in cell_str for kw in keywords)


def _find_header_row(ws, max_rows: int = 20) -> tuple[int, dict[str, int]] | None:
    """Scan worksheet for a header row that contains item-related keywords."""
    for row_idx in range(1, min(max_rows + 1, ws.max_row + 1)):
        col_map = {}
        for col_idx in range(1, min(20, ws.max_column + 1)):
            cell_value = ws.cell(row=row_idx, column=col_idx).value
            if cell_value is None:
                continue
            cell_str = str(cell_value).lower().strip()
            for field_name, keywords in HEADER_KEYWORDS.items():
                if field_name not in col_map:
                    for kw in keywords:
                        if kw.lower() in cell_str:
                            col_map[field_name] = col_idx
                            break

        if "description" in col_map:
            return row_idx, col_map

    return None


def _extract_metadata(ws, header_row: int) -> dict:
    """Extract metadata from cells above the header row."""
    metadata = {}

    for row_idx in range(1, header_row):
        for col_idx in range(1, min(10, ws.max_column + 1)):
            cell_value = ws.cell(row=row_idx, column=col_idx).value
            if cell_value is None:
                continue
            cell_str = str(cell_value)

            for meta_key, keywords in METADATA_KEYWORDS.items():
                if meta_key in metadata:
                    continue
                if _cell_matches_keywords(cell_value, keywords):
                    # The value is likely in the next column or after a colon
                    next_val = ws.cell(row=row_idx, column=col_idx + 1).value
                    if next_val is not None:
                        metadata[meta_key] = next_val
                    else:
                        # Try to extract from the same cell after separator
                        for sep in [":", "：", "\t"]:
                            if sep in cell_str:
                                metadata[meta_key] = cell_str.split(sep, 1)[1].strip()
                                break

    return metadata


class ExcelParser(QuoteParser):
    """Extract quote data from Excel (.xlsx) files."""

    def parse(self, source: bytes | str, metadata: dict | None = None) -> ParsedQuote | None:
        """Parse an Excel file.

        Args:
            source: File path (str) or Excel bytes.
            metadata: Additional context.
        """
        metadata = metadata or {}

        if isinstance(source, str):
            file_path = Path(source)
            if not file_path.exists():
                return None
            wb = load_workbook(file_path, read_only=True, data_only=True)
        else:
            import io
            wb = load_workbook(io.BytesIO(source), read_only=True, data_only=True)

        try:
            # Try each worksheet
            for ws in wb.worksheets:
                result = self._parse_worksheet(ws, metadata)
                if result and (result.line_items or result.total_amount):
                    return result

            return None
        finally:
            wb.close()

    def _parse_worksheet(self, ws, metadata: dict) -> ParsedQuote | None:
        """Parse a single worksheet."""
        header_result = _find_header_row(ws)
        if header_result is None:
            return None

        header_row_idx, col_map = header_result

        # Extract metadata from cells above the header
        sheet_meta = _extract_metadata(ws, header_row_idx)

        quote = ParsedQuote(
            supplier_name=metadata.get("sender_name"),
            supplier_email=metadata.get("sender_email"),
            quote_number=str(sheet_meta.get("quote_number", "")) or None,
            quote_date=str(sheet_meta.get("quote_date", "")) or None,
            validity_date=str(sheet_meta.get("validity_date", "")) or None,
            delivery_date=str(sheet_meta.get("delivery_date", "")) or None,
            payment_terms=str(sheet_meta.get("payment_terms", "")) or None,
        )

        # Parse total from metadata
        if "total_amount" in sheet_meta:
            quote.total_amount = _parse_number(sheet_meta["total_amount"])

        # Parse line items starting from the row after the header
        for row_idx in range(header_row_idx + 1, ws.max_row + 1):
            desc_col = col_map["description"]
            desc_value = ws.cell(row=row_idx, column=desc_col).value

            if desc_value is None or str(desc_value).strip() == "":
                # Check if this is an empty row (skip) or end of data
                # Allow up to 2 consecutive empty rows
                next_val = ws.cell(row=row_idx + 1, column=desc_col).value if row_idx < ws.max_row else None
                if next_val is None:
                    break
                continue

            desc_str = str(desc_value).strip()

            # Skip total/subtotal rows
            if any(kw in desc_str.lower() for kw in ["合計", "total", "小計", "消費税", "税"]):
                # But try to capture the total amount
                if "amount" in col_map:
                    amt = _parse_number(ws.cell(row=row_idx, column=col_map["amount"]).value)
                    if amt and "合計" in desc_str.lower() or "total" in desc_str.lower():
                        quote.total_amount = amt
                continue

            item = ParsedLineItem(
                item_number=len(quote.line_items) + 1,
                description=desc_str,
            )

            if "quantity" in col_map:
                item.quantity = _parse_number(ws.cell(row=row_idx, column=col_map["quantity"]).value)

            if "unit" in col_map:
                unit_val = ws.cell(row=row_idx, column=col_map["unit"]).value
                item.unit = str(unit_val).strip() if unit_val else None

            if "unit_price" in col_map:
                item.unit_price = _parse_number(
                    ws.cell(row=row_idx, column=col_map["unit_price"]).value
                )

            if "amount" in col_map:
                item.amount = _parse_number(ws.cell(row=row_idx, column=col_map["amount"]).value)

            quote.line_items.append(item)

        # Calculate confidence
        if quote.line_items and quote.total_amount:
            quote.confidence = 0.9
        elif quote.line_items:
            quote.confidence = 0.7
        elif quote.total_amount:
            quote.confidence = 0.4
        else:
            return None

        return quote
