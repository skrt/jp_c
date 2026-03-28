"""Tests for email body parser."""

from decimal import Decimal

from quote_manager.parsers.email_body import EmailBodyParser


class TestEmailBodyParser:
    def setup_method(self):
        self.parser = EmailBodyParser()

    def test_parse_japanese_quote_email(self):
        """Test parsing a typical Japanese quote email."""
        body = """
株式会社テスト 御中

お見積書をお送りいたします。

見積番号: Q-2026-001
見積日: 2026/03/15

・サーバー機器 A100  ¥500,000
・ネットワーク機器 SW-200  ¥120,000
・設置工事費  ¥80,000

合計: ¥700,000

納期: 2026年4月末
支払条件: 月末締め翌月末払い
有効期限: 2026年4月15日

よろしくお願いいたします。
株式会社サプライヤーA
"""
        result = self.parser.parse(body, {"sender_name": "サプライヤーA", "sender_email": "a@example.com"})

        assert result is not None
        assert result.quote_number == "Q-2026-001"
        assert result.total_amount == Decimal("700000")
        assert len(result.line_items) == 3
        assert result.line_items[0].description == "サーバー機器 A100"
        assert result.line_items[0].amount == Decimal("500000")
        assert result.supplier_name == "サプライヤーA"
        assert result.confidence >= 0.5

    def test_parse_email_with_table_format(self):
        """Test parsing email with qty x price format."""
        body = """
見積書

品名             数量  単価       金額
--------------------------------------
ノートPC X500     10  ×  ¥150,000  ¥1,500,000
モニター 27inch    10  ×  ¥50,000   ¥500,000

合計金額: ¥2,000,000
"""
        result = self.parser.parse(body)

        assert result is not None
        assert result.total_amount == Decimal("2000000")
        assert len(result.line_items) >= 1

    def test_parse_empty_body(self):
        """Test parsing empty email body returns None."""
        result = self.parser.parse("")
        assert result is None

    def test_parse_non_quote_email(self):
        """Test parsing a non-quote email returns None."""
        body = """
こんにちは。
先日の打ち合わせのお礼を申し上げます。
来週もよろしくお願いいたします。
"""
        result = self.parser.parse(body)
        assert result is None

    def test_parse_total_only(self):
        """Test parsing email with only total amount."""
        body = """
お見積りの件、合計金額は ¥350,000 となります。
詳細は添付ファイルをご確認ください。
"""
        result = self.parser.parse(body)
        assert result is not None
        assert result.total_amount == Decimal("350000")

    def test_extract_delivery_info(self):
        """Test delivery and payment terms extraction."""
        body = """
・部品A  ¥100,000

合計: ¥100,000
納期: 発注後2週間
支払条件: 前払い
有効期限: 2026/04/30
"""
        result = self.parser.parse(body)
        assert result is not None
        assert "2週間" in result.delivery_date
        assert "前払い" in result.payment_terms
