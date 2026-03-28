"""Build comparison tables across multiple supplier quotes."""

from dataclasses import dataclass, field
from decimal import Decimal
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from quote_manager.models import Project, Quote, LineItem, Supplier

SIMILARITY_THRESHOLD = 0.6


@dataclass
class ComparisonCell:
    """A single cell in the comparison table for one supplier's quote on one item."""
    supplier_id: int
    supplier_name: str
    quote_id: int
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    is_lowest: bool = False


@dataclass
class ComparisonRow:
    """A row in the comparison table representing one line item across suppliers."""
    item_number: int
    description: str
    cells: list[ComparisonCell] = field(default_factory=list)

    @property
    def lowest_amount(self) -> Decimal | None:
        amounts = [c.amount for c in self.cells if c.amount is not None]
        return min(amounts) if amounts else None


@dataclass
class ComparisonSummary:
    """Summary row for each supplier."""
    supplier_id: int
    supplier_name: str
    quote_id: int
    total_amount: Decimal | None = None
    delivery_date: str | None = None
    delivery_days: int | None = None
    payment_terms: str | None = None
    validity_date: str | None = None
    is_lowest_total: bool = False


@dataclass
class ComparisonTable:
    """Complete comparison table for a project."""
    project_name: str
    suppliers: list[dict]  # [{id, name, quote_id}]
    rows: list[ComparisonRow] = field(default_factory=list)
    summaries: list[ComparisonSummary] = field(default_factory=list)


def _normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    import re
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[（）()「」【】\[\]{}]", "", text)
    return text


def _similarity(a: str, b: str) -> float:
    """Calculate text similarity between two item descriptions."""
    a_norm = _normalize_text(a)
    b_norm = _normalize_text(b)

    if a_norm == b_norm:
        return 1.0

    return SequenceMatcher(None, a_norm, b_norm).ratio()


def _align_items(all_items: dict[int, list[LineItem]]) -> list[tuple[str, dict[int, LineItem]]]:
    """Align line items across suppliers using fuzzy matching.

    Args:
        all_items: {quote_id: [LineItem, ...]}

    Returns:
        List of (canonical_description, {quote_id: LineItem})
    """
    if not all_items:
        return []

    # Use the first supplier's items as the base
    quote_ids = list(all_items.keys())
    base_id = quote_ids[0]
    base_items = all_items[base_id]

    aligned: list[tuple[str, dict[int, LineItem]]] = []

    for base_item in base_items:
        row_map = {base_id: base_item}
        aligned.append((base_item.description, row_map))

    # Match other suppliers' items to the base
    for other_id in quote_ids[1:]:
        other_items = list(all_items[other_id])
        used_indices = set()

        for row_desc, row_map in aligned:
            best_match_idx = None
            best_score = 0.0

            for idx, other_item in enumerate(other_items):
                if idx in used_indices:
                    continue
                score = _similarity(row_desc, other_item.description)
                if score > best_score:
                    best_score = score
                    best_match_idx = idx

            if best_match_idx is not None and best_score >= SIMILARITY_THRESHOLD:
                row_map[other_id] = other_items[best_match_idx]
                used_indices.add(best_match_idx)

        # Add unmatched items as new rows
        for idx, other_item in enumerate(other_items):
            if idx not in used_indices:
                aligned.append((other_item.description, {other_id: other_item}))

    return aligned


def build_comparison(session: Session, project_id: int) -> ComparisonTable | None:
    """Build a comparison table for all quotes in a project.

    Args:
        session: Database session.
        project_id: Project ID.

    Returns:
        ComparisonTable or None if no quotes exist.
    """
    project = session.query(Project).get(project_id)
    if not project:
        return None

    quotes = session.query(Quote).filter_by(project_id=project_id).all()
    if not quotes:
        return None

    # Build supplier info and collect items
    suppliers = []
    all_items: dict[int, list[LineItem]] = {}

    for quote in quotes:
        supplier = session.query(Supplier).get(quote.supplier_id)
        suppliers.append({
            "id": supplier.id,
            "name": supplier.name,
            "quote_id": quote.id,
        })
        all_items[quote.id] = list(quote.line_items)

    # Align items
    aligned = _align_items(all_items)

    # Build comparison rows
    rows = []
    for idx, (desc, item_map) in enumerate(aligned):
        row = ComparisonRow(item_number=idx + 1, description=desc)

        for sup in suppliers:
            qid = sup["quote_id"]
            item = item_map.get(qid)

            cell = ComparisonCell(
                supplier_id=sup["id"],
                supplier_name=sup["name"],
                quote_id=qid,
            )
            if item:
                cell.quantity = item.quantity
                cell.unit = item.unit
                cell.unit_price = item.unit_price
                cell.amount = item.amount

            row.cells.append(cell)

        # Mark lowest price
        lowest = row.lowest_amount
        if lowest is not None:
            for cell in row.cells:
                if cell.amount == lowest:
                    cell.is_lowest = True

        rows.append(row)

    # Build summaries
    summaries = []
    for quote in quotes:
        supplier = session.query(Supplier).get(quote.supplier_id)
        summaries.append(ComparisonSummary(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            quote_id=quote.id,
            total_amount=quote.total_amount,
            delivery_date=quote.delivery_date,
            delivery_days=quote.delivery_days,
            payment_terms=quote.payment_terms,
            validity_date=str(quote.validity_date) if quote.validity_date else None,
        ))

    # Mark lowest total
    totals = [s.total_amount for s in summaries if s.total_amount is not None]
    if totals:
        lowest_total = min(totals)
        for s in summaries:
            if s.total_amount == lowest_total:
                s.is_lowest_total = True

    return ComparisonTable(
        project_name=project.name,
        suppliers=suppliers,
        rows=rows,
        summaries=summaries,
    )
