"""Tests for comparison service."""

from decimal import Decimal

from quote_manager.models import Project, Supplier, Quote, LineItem
from quote_manager.services.comparison import build_comparison, _similarity, _normalize_text


class TestSimilarity:
    def test_exact_match(self):
        assert _similarity("サーバー A100", "サーバー A100") == 1.0

    def test_similar_items(self):
        score = _similarity("サーバー機器 A100", "サーバー A100")
        assert score >= 0.6

    def test_different_items(self):
        score = _similarity("サーバー", "ネットワークスイッチ")
        assert score < 0.5

    def test_normalize(self):
        assert _normalize_text("  サーバー（高性能）  ") == "サーバー高性能"


class TestBuildComparison:
    def test_basic_comparison(self, db_session, sample_project, sample_suppliers):
        """Test building a comparison table with multiple suppliers."""
        project = sample_project
        sup_a, sup_b, sup_c = sample_suppliers

        # Create quotes
        quotes = []
        for sup, total, prices in [
            (sup_a, 700000, [500000, 120000, 80000]),
            (sup_b, 680000, [480000, 130000, 70000]),
            (sup_c, 720000, [510000, 110000, 100000]),
        ]:
            q = Quote(
                project_id=project.id,
                supplier_id=sup.id,
                total_amount=Decimal(str(total)),
                source_type="test",
                currency="JPY",
            )
            db_session.add(q)
            db_session.flush()

            for i, (desc, price) in enumerate(
                zip(["サーバー機器", "ネットワーク機器", "設置工事"], prices)
            ):
                li = LineItem(
                    quote_id=q.id,
                    item_number=i + 1,
                    description=desc,
                    quantity=Decimal("1"),
                    amount=Decimal(str(price)),
                )
                db_session.add(li)

            quotes.append(q)

        db_session.commit()

        table = build_comparison(db_session, project.id)

        assert table is not None
        assert table.project_name == "テスト案件"
        assert len(table.suppliers) == 3
        assert len(table.rows) == 3
        assert len(table.summaries) == 3

        # Check lowest total is B社 at 680,000
        for summary in table.summaries:
            if summary.supplier_name == "B社":
                assert summary.is_lowest_total is True
            else:
                assert summary.is_lowest_total is False

        # Check lowest per item
        for row in table.rows:
            lowest = row.lowest_amount
            assert lowest is not None
            for cell in row.cells:
                if cell.amount == lowest:
                    assert cell.is_lowest is True

    def test_empty_project(self, db_session, sample_project):
        """Test comparison with no quotes returns None."""
        table = build_comparison(db_session, sample_project.id)
        assert table is None

    def test_nonexistent_project(self, db_session):
        """Test comparison with invalid project ID."""
        table = build_comparison(db_session, 99999)
        assert table is None
