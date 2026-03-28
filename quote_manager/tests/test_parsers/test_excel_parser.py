"""Tests for Excel parser."""

import tempfile
from decimal import Decimal

from openpyxl import Workbook

from quote_manager.parsers.excel_parser import ExcelParser


def _create_test_excel(rows: list[list], metadata_rows: list[list] | None = None) -> str:
    """Create a temporary Excel file with given data."""
    wb = Workbook()
    ws = wb.active

    row_idx = 1

    # Write metadata rows above the header
    if metadata_rows:
        for meta_row in metadata_rows:
            for col_idx, value in enumerate(meta_row, 1):
                ws.cell(row=row_idx, column=col_idx, value=value)
            row_idx += 1

    # Write data rows (first row is header)
    for row_data in rows:
        for col_idx, value in enumerate(row_data, 1):
            ws.cell(row=row_idx, column=col_idx, value=value)
        row_idx += 1

    path = tempfile.mktemp(suffix=".xlsx")
    wb.save(path)
    return path


class TestExcelParser:
    def setup_method(self):
        self.parser = ExcelParser()

    def test_parse_basic_quote(self):
        """Test parsing a basic Excel quote."""
        path = _create_test_excel(
            rows=[
                ["品名", "数量", "単位", "単価", "金額"],
                ["サーバー A100", 2, "台", 300000, 600000],
                ["メモリ 64GB", 4, "枚", 50000, 200000],
                ["SSD 2TB", 2, "個", 80000, 160000],
            ],
            metadata_rows=[
                ["見積番号", "Q-001"],
                ["見積日", "2026/03/15"],
            ],
        )

        result = self.parser.parse(path)
        assert result is not None
        assert len(result.line_items) == 3
        assert result.line_items[0].description == "サーバー A100"
        assert result.line_items[0].quantity == Decimal("2")
        assert result.line_items[0].unit_price == Decimal("300000")
        assert result.line_items[0].amount == Decimal("600000")
        assert result.confidence >= 0.7

    def test_parse_with_total_row(self):
        """Test that total rows are extracted correctly."""
        path = _create_test_excel(
            rows=[
                ["品名", "数量", "単価", "金額"],
                ["品目A", 1, 100000, 100000],
                ["品目B", 2, 50000, 100000],
                ["合計", None, None, 200000],
            ],
        )

        result = self.parser.parse(path)
        assert result is not None
        assert len(result.line_items) == 2
        assert result.total_amount == Decimal("200000")

    def test_parse_english_headers(self):
        """Test parsing Excel with English column headers."""
        path = _create_test_excel(
            rows=[
                ["Item", "Description", "Qty", "Unit Price", "Amount"],
                [1, "Server", 1, 500000, 500000],
                [2, "Switch", 2, 100000, 200000],
            ],
        )

        result = self.parser.parse(path)
        assert result is not None
        assert len(result.line_items) == 2

    def test_parse_nonexistent_file(self):
        """Test parsing a nonexistent file returns None."""
        result = self.parser.parse("/nonexistent/file.xlsx")
        assert result is None

    def test_parse_no_header(self):
        """Test parsing Excel without recognizable headers returns None."""
        path = _create_test_excel(
            rows=[
                ["foo", "bar", "baz"],
                [1, 2, 3],
            ],
        )

        result = self.parser.parse(path)
        assert result is None
