"""Quote parsers for various input formats."""

from quote_manager.parsers.base import ParsedQuote, ParsedLineItem, QuoteParser
from quote_manager.parsers.email_body import EmailBodyParser
from quote_manager.parsers.pdf_parser import PdfParser
from quote_manager.parsers.excel_parser import ExcelParser
from quote_manager.parsers.ai_extractor import AiExtractor

__all__ = [
    "ParsedQuote",
    "ParsedLineItem",
    "QuoteParser",
    "EmailBodyParser",
    "PdfParser",
    "ExcelParser",
    "AiExtractor",
]
