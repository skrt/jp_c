"""Tests for export service."""

import tempfile
from decimal import Decimal
from pathlib import Path

from quote_manager.services.comparison import (
    ComparisonTable,
    ComparisonRow,
    ComparisonCell,
    ComparisonSummary,
)
from quote_manager.services.export import export_to_excel


def _create_sample_table() -> ComparisonTable:
    """Create a sample comparison table for testing."""
    suppliers = [
        {"id": 1, "name": "A社", "quote_id": 1},
        {"id": 2, "name": "B社", "quote_id": 2},
    ]

    rows = [
        ComparisonRow(
            item_number=1,
            description="サーバー機器 A100",
            cells=[
                ComparisonCell(supplier_id=1, supplier_name="A社", quote_id=1,
                             quantity=Decimal("2"), unit_price=Decimal("300000"),
                             amount=Decimal("600000"), is_lowest=False),
                ComparisonCell(supplier_id=2, supplier_name="B社", quote_id=2,
                             quantity=Decimal("2"), unit_price=Decimal("280000"),
                             amount=Decimal("560000"), is_lowest=True),
            ],
        ),
        ComparisonRow(
            item_number=2,
            description="設置工事費",
            cells=[
                ComparisonCell(supplier_id=1, supplier_name="A社", quote_id=1,
                             amount=Decimal("80000"), is_lowest=True),
                ComparisonCell(supplier_id=2, supplier_name="B社", quote_id=2,
                             amount=Decimal("100000"), is_lowest=False),
            ],
        ),
    ]

    summaries = [
        ComparisonSummary(supplier_id=1, supplier_name="A社", quote_id=1,
                         total_amount=Decimal("680000"), delivery_date="4月末",
                         payment_terms="月末締め", is_lowest_total=False),
        ComparisonSummary(supplier_id=2, supplier_name="B社", quote_id=2,
                         total_amount=Decimal("660000"), delivery_date="3週間",
                         payment_terms="前払い", is_lowest_total=True),
    ]

    return ComparisonTable(
        project_name="テスト案件",
        suppliers=suppliers,
        rows=rows,
        summaries=summaries,
    )


class TestExcelExport:
    def test_export_creates_file(self):
        """Test that Excel export creates a valid file."""
        table = _create_sample_table()
        output = tempfile.mktemp(suffix=".xlsx")

        result_path = export_to_excel(table, output)

        assert Path(result_path).exists()
        assert Path(result_path).stat().st_size > 0

    def test_export_content(self):
        """Test that exported Excel contains correct data."""
        from openpyxl import load_workbook

        table = _create_sample_table()
        output = tempfile.mktemp(suffix=".xlsx")
        export_to_excel(table, output)

        wb = load_workbook(output)
        ws = wb.active

        # Check title
        assert "テスト案件" in str(ws.cell(row=1, column=1).value)

        # Check headers exist
        assert ws.cell(row=3, column=1).value == "No."
        assert ws.cell(row=3, column=3).value == "A社"
        assert ws.cell(row=3, column=4).value == "B社"

        wb.close()
