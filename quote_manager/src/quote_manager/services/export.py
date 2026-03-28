"""Export comparison tables to Excel and PDF."""

from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill, numbers
from openpyxl.utils import get_column_letter
from jinja2 import Environment, FileSystemLoader

from quote_manager.services.comparison import ComparisonTable


# Styles
HEADER_FONT = Font(name="Yu Gothic", bold=True, size=11, color="FFFFFF")
HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
LOWEST_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
RIGHT = Alignment(horizontal="right", vertical="center")
JPY_FORMAT = '#,##0"円"'
NUMBER_FORMAT = "#,##0"


def _format_currency(amount: Decimal | None, currency: str = "JPY") -> str:
    if amount is None:
        return "-"
    if currency == "JPY":
        return f"¥{amount:,.0f}"
    return f"${amount:,.2f}"


def export_to_excel(table: ComparisonTable, output_path: str) -> str:
    """Export comparison table to an Excel file.

    Args:
        table: ComparisonTable to export.
        output_path: Output file path.

    Returns:
        Path to the created Excel file.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "見積比較表"

    num_suppliers = len(table.suppliers)

    # === Title Row ===
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=2 + num_suppliers)
    title_cell = ws.cell(row=1, column=1, value=f"見積比較表 - {table.project_name}")
    title_cell.font = Font(name="Yu Gothic", bold=True, size=14)
    title_cell.alignment = CENTER
    ws.row_dimensions[1].height = 35

    # === Header Row ===
    row = 3
    headers = ["No.", "品名・説明"]
    for sup in table.suppliers:
        headers.append(sup["name"])

    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=row, column=col_idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER
        cell.border = THIN_BORDER

    # === Line Item Rows ===
    for comp_row in table.rows:
        row += 1

        # Item number
        cell = ws.cell(row=row, column=1, value=comp_row.item_number)
        cell.alignment = CENTER
        cell.border = THIN_BORDER

        # Description
        cell = ws.cell(row=row, column=2, value=comp_row.description)
        cell.alignment = LEFT
        cell.border = THIN_BORDER

        # Supplier amounts
        for idx, comp_cell in enumerate(comp_row.cells):
            col = 3 + idx
            if comp_cell.amount is not None:
                cell = ws.cell(row=row, column=col, value=float(comp_cell.amount))
                cell.number_format = JPY_FORMAT
            elif comp_cell.unit_price is not None:
                # Show as "qty x unit_price"
                qty = comp_cell.quantity or 1
                cell = ws.cell(row=row, column=col, value=float(comp_cell.unit_price * qty))
                cell.number_format = JPY_FORMAT
            else:
                cell = ws.cell(row=row, column=col, value="-")

            cell.alignment = RIGHT
            cell.border = THIN_BORDER

            if comp_cell.is_lowest:
                cell.fill = LOWEST_FILL

    # === Summary Section ===
    row += 2

    # Total row
    summary_labels = ["合計金額", "納期", "支払条件", "見積有効期限"]
    summary_keys = ["total_amount", "delivery_date", "payment_terms", "validity_date"]

    for label, key in zip(summary_labels, summary_keys):
        cell = ws.cell(row=row, column=1)
        cell.border = THIN_BORDER
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
        cell = ws.cell(row=row, column=1, value=label)
        cell.font = Font(name="Yu Gothic", bold=True, size=11)
        cell.alignment = CENTER
        cell.border = THIN_BORDER

        for idx, summary in enumerate(table.summaries):
            col = 3 + idx
            value = getattr(summary, key, None)

            if key == "total_amount" and value is not None:
                cell = ws.cell(row=row, column=col, value=float(value))
                cell.number_format = JPY_FORMAT
                if summary.is_lowest_total:
                    cell.fill = LOWEST_FILL
            else:
                cell = ws.cell(row=row, column=col, value=str(value) if value else "-")

            cell.alignment = RIGHT if key == "total_amount" else CENTER
            cell.border = THIN_BORDER

        row += 1

    # === Column widths ===
    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 40
    for i in range(num_suppliers):
        col_letter = get_column_letter(3 + i)
        ws.column_dimensions[col_letter].width = 20

    # Save
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(output))
    return str(output)


def export_to_pdf(table: ComparisonTable, output_path: str) -> str:
    """Export comparison table to a PDF file.

    Args:
        table: ComparisonTable to export.
        output_path: Output file path.

    Returns:
        Path to the created PDF file.
    """
    # Load template
    template_dir = Path(__file__).parent.parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    env.filters["currency"] = _format_currency

    template = env.get_template("comparison.html")

    html = template.render(
        table=table,
        format_currency=_format_currency,
    )

    # Convert to PDF using WeasyPrint
    from weasyprint import HTML

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html).write_pdf(str(output))

    return str(output)
