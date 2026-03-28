"""AI-powered quote extraction using Claude API as a fallback parser."""

import json
from decimal import Decimal

from quote_manager.parsers.base import QuoteParser, ParsedQuote, ParsedLineItem
from quote_manager.config import get_settings

EXTRACTION_PROMPT = """あなたは見積書データ抽出の専門家です。以下のテキストから見積もり情報を構造化されたJSONとして抽出してください。

抽出するフィールド:
- supplier_name: サプライヤー/見積元の会社名
- quote_number: 見積番号
- quote_date: 見積日（YYYY-MM-DD形式）
- validity_date: 有効期限（YYYY-MM-DD形式）
- delivery_date: 納期（テキストそのまま）
- delivery_days: 納期日数（数値）
- total_amount: 合計金額（数値、カンマなし）
- currency: 通貨（JPY, USD等）
- payment_terms: 支払条件
- notes: 備考
- line_items: 明細行の配列。各行は以下のフィールド:
  - item_number: 行番号
  - description: 品名・説明
  - quantity: 数量（数値）
  - unit: 単位
  - unit_price: 単価（数値）
  - amount: 金額（数値）
  - notes: 備考

JSONのみを返してください。抽出できない項目はnullにしてください。

テキスト:
{text}"""


class AiExtractor(QuoteParser):
    """Use Claude API to extract structured quote data from unstructured text."""

    def parse(self, source: bytes | str, metadata: dict | None = None) -> ParsedQuote | None:
        if isinstance(source, bytes):
            source = source.decode("utf-8", errors="replace")

        if not source.strip():
            return None

        settings = get_settings()
        if not settings.anthropic_api_key:
            return None

        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        # Truncate very long texts
        max_chars = 10000
        text = source[:max_chars]

        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": EXTRACTION_PROMPT.format(text=text),
                    }
                ],
            )
        except Exception:
            return None

        # Extract JSON from response
        response_text = response.content[0].text
        try:
            # Try to find JSON in the response
            json_match = response_text
            if "```" in response_text:
                # Extract from code block
                start = response_text.find("```")
                end = response_text.rfind("```")
                if start != end:
                    json_match = response_text[start:end]
                    # Remove ```json prefix
                    json_match = json_match.lstrip("`").lstrip("json").lstrip("\n")

            data = json.loads(json_match)
        except json.JSONDecodeError:
            return None

        metadata = metadata or {}

        quote = ParsedQuote(
            supplier_name=data.get("supplier_name") or metadata.get("sender_name"),
            supplier_email=metadata.get("sender_email"),
            quote_number=data.get("quote_number"),
            quote_date=data.get("quote_date"),
            validity_date=data.get("validity_date"),
            delivery_date=data.get("delivery_date"),
            delivery_days=data.get("delivery_days"),
            currency=data.get("currency", "JPY"),
            payment_terms=data.get("payment_terms"),
            notes=data.get("notes"),
            raw_text=source,
            confidence=0.85,  # AI extraction is generally reliable
        )

        if data.get("total_amount") is not None:
            try:
                quote.total_amount = Decimal(str(data["total_amount"]))
            except Exception:
                pass

        for li_data in data.get("line_items", []):
            item = ParsedLineItem(
                item_number=li_data.get("item_number"),
                description=li_data.get("description", ""),
                unit=li_data.get("unit"),
                notes=li_data.get("notes"),
            )
            if li_data.get("quantity") is not None:
                try:
                    item.quantity = Decimal(str(li_data["quantity"]))
                except Exception:
                    pass
            if li_data.get("unit_price") is not None:
                try:
                    item.unit_price = Decimal(str(li_data["unit_price"]))
                except Exception:
                    pass
            if li_data.get("amount") is not None:
                try:
                    item.amount = Decimal(str(li_data["amount"]))
                except Exception:
                    pass

            quote.line_items.append(item)

        return quote
