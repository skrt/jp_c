"""Orchestrates fetching, parsing, and storing quotes from Gmail and Slack."""

import json
from datetime import date

from sqlalchemy.orm import Session

from quote_manager.models import Project, Supplier, Quote, LineItem, EmailRecord
from quote_manager.gmail.fetcher import fetch_emails, RawEmail
from quote_manager.slack.fetcher import fetch_channel_messages, fetch_thread_messages, SlackMessage
from quote_manager.parsers.base import ParsedQuote
from quote_manager.parsers.email_body import EmailBodyParser
from quote_manager.parsers.pdf_parser import PdfParser
from quote_manager.parsers.excel_parser import ExcelParser
from quote_manager.parsers.ai_extractor import AiExtractor

AI_CONFIDENCE_THRESHOLD = 0.4  # Use AI fallback when confidence is below this


def _get_or_create_supplier(session: Session, name: str | None, email: str | None) -> Supplier:
    """Find an existing supplier or create a new one."""
    if email:
        supplier = session.query(Supplier).filter_by(email=email).first()
        if supplier:
            return supplier

    if name:
        supplier = session.query(Supplier).filter_by(name=name).first()
        if supplier:
            return supplier

    # Create new supplier
    supplier_name = name or email or "不明"
    supplier = Supplier(name=supplier_name, email=email)
    session.add(supplier)
    session.flush()
    return supplier


def _parsed_to_quote(
    session: Session,
    parsed: ParsedQuote,
    project: Project,
    source_type: str,
    source_path: str | None = None,
) -> Quote:
    """Convert a ParsedQuote to a database Quote record."""
    supplier = _get_or_create_supplier(session, parsed.supplier_name, parsed.supplier_email)

    quote = Quote(
        project_id=project.id,
        supplier_id=supplier.id,
        quote_number=parsed.quote_number,
        quote_date=_parse_date(parsed.quote_date),
        validity_date=_parse_date(parsed.validity_date),
        delivery_date=parsed.delivery_date,
        delivery_days=parsed.delivery_days,
        total_amount=parsed.total_amount,
        currency=parsed.currency,
        payment_terms=parsed.payment_terms,
        notes=parsed.notes,
        source_type=source_type,
        source_path=source_path,
        raw_text=parsed.raw_text[:5000] if parsed.raw_text else None,
    )
    session.add(quote)
    session.flush()

    for li in parsed.line_items:
        line_item = LineItem(
            quote_id=quote.id,
            item_number=li.item_number,
            description=li.description,
            quantity=li.quantity,
            unit=li.unit,
            unit_price=li.unit_price,
            amount=li.amount,
            notes=li.notes,
        )
        session.add(line_item)

    return quote


def _parse_date(date_str: str | None) -> date | None:
    """Try to parse a date string in various formats."""
    if not date_str:
        return None

    import re

    # YYYY-MM-DD or YYYY/MM/DD
    match = re.match(r"(\d{4})[/\-年](\d{1,2})[/\-月](\d{1,2})", date_str)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass
    return None


def _is_already_processed(session: Session, message_id: str) -> bool:
    """Check if a message has already been processed."""
    return session.query(EmailRecord).filter_by(message_id=message_id).first() is not None


def _try_parse_with_fallback(
    source: bytes | str,
    primary_parser,
    metadata: dict,
) -> ParsedQuote | None:
    """Try primary parser, fall back to AI if confidence is low."""
    result = primary_parser.parse(source, metadata)

    if result and result.confidence >= AI_CONFIDENCE_THRESHOLD:
        return result

    # Try AI fallback
    ai = AiExtractor()
    text = source if isinstance(source, str) else source.decode("utf-8", errors="replace")
    ai_result = ai.parse(text, metadata)

    if ai_result:
        return ai_result

    return result  # Return low-confidence result if AI also fails


def ingest_gmail(session: Session, project: Project) -> list[Quote]:
    """Fetch and parse quotes from Gmail for a project.

    Args:
        session: Database session.
        project: Project to fetch quotes for.

    Returns:
        List of newly created Quote records.
    """
    if not project.gmail_query:
        return []

    emails = fetch_emails(project.gmail_query)
    new_quotes = []

    email_parser = EmailBodyParser()
    pdf_parser = PdfParser()
    excel_parser = ExcelParser()

    for raw_email in emails:
        if _is_already_processed(session, raw_email.message_id):
            continue

        metadata = {
            "sender_name": raw_email.sender,
            "sender_email": raw_email.sender_email,
            "subject": raw_email.subject,
        }

        # Record the email
        record = EmailRecord(
            message_id=raw_email.message_id,
            source="gmail",
            project_id=project.id,
            subject=raw_email.subject,
            sender=raw_email.sender_email,
            received_at=raw_email.date,
            processed=True,
            attachment_paths=json.dumps(raw_email.attachment_paths) if raw_email.attachment_paths else None,
        )
        session.add(record)

        # Parse email body
        if raw_email.body_text:
            parsed = _try_parse_with_fallback(raw_email.body_text, email_parser, metadata)
            if parsed:
                quote = _parsed_to_quote(session, parsed, project, "email_body")
                new_quotes.append(quote)

        # Parse attachments
        for att_path in raw_email.attachment_paths:
            lower_path = att_path.lower()
            if lower_path.endswith(".pdf"):
                parsed = _try_parse_with_fallback(att_path, pdf_parser, metadata)
                if parsed:
                    quote = _parsed_to_quote(session, parsed, project, "pdf", att_path)
                    new_quotes.append(quote)
            elif lower_path.endswith((".xlsx", ".xls")):
                parsed = _try_parse_with_fallback(att_path, excel_parser, metadata)
                if parsed:
                    quote = _parsed_to_quote(session, parsed, project, "excel", att_path)
                    new_quotes.append(quote)

    session.commit()
    return new_quotes


def ingest_slack(session: Session, project: Project) -> list[Quote]:
    """Fetch and parse quotes from Slack for a project.

    Args:
        session: Database session.
        project: Project with slack_channel_id and optionally slack_thread_ts.

    Returns:
        List of newly created Quote records.
    """
    if not project.slack_channel_id:
        return []

    # Fetch messages from thread or channel
    if project.slack_thread_ts:
        messages = fetch_thread_messages(project.slack_channel_id, project.slack_thread_ts)
    else:
        messages = fetch_channel_messages(
            project.slack_channel_id, keyword="見積"
        )

    new_quotes = []
    email_parser = EmailBodyParser()
    pdf_parser = PdfParser()
    excel_parser = ExcelParser()

    for msg in messages:
        if _is_already_processed(session, msg.message_id):
            continue

        metadata = {
            "sender_name": msg.sender_name,
            "sender_email": None,
        }

        # Record the message
        record = EmailRecord(
            message_id=msg.message_id,
            source="slack",
            project_id=project.id,
            subject=f"Slack: {msg.text[:100]}",
            sender=msg.sender_name,
            received_at=msg.timestamp,
            processed=True,
            attachment_paths=json.dumps(msg.attachment_paths) if msg.attachment_paths else None,
        )
        session.add(record)

        # Parse message text
        if msg.text:
            parsed = _try_parse_with_fallback(msg.text, email_parser, metadata)
            if parsed:
                quote = _parsed_to_quote(session, parsed, project, "slack")
                new_quotes.append(quote)

        # Parse attachments
        for att_path in msg.attachment_paths:
            lower_path = att_path.lower()
            if lower_path.endswith(".pdf"):
                parsed = _try_parse_with_fallback(att_path, pdf_parser, metadata)
                if parsed:
                    quote = _parsed_to_quote(session, parsed, project, "pdf", att_path)
                    new_quotes.append(quote)
            elif lower_path.endswith((".xlsx", ".xls")):
                parsed = _try_parse_with_fallback(att_path, excel_parser, metadata)
                if parsed:
                    quote = _parsed_to_quote(session, parsed, project, "excel", att_path)
                    new_quotes.append(quote)

    session.commit()
    return new_quotes


def ingest_file(session: Session, project: Project, file_path: str, supplier_name: str | None = None) -> Quote | None:
    """Manually ingest a single file (PDF or Excel) into a project.

    Args:
        session: Database session.
        project: Target project.
        file_path: Path to the file.
        supplier_name: Optional supplier name override.

    Returns:
        Created Quote record or None.
    """
    metadata = {"sender_name": supplier_name}
    lower_path = file_path.lower()

    if lower_path.endswith(".pdf"):
        parser = PdfParser()
    elif lower_path.endswith((".xlsx", ".xls")):
        parser = ExcelParser()
    else:
        return None

    parsed = _try_parse_with_fallback(file_path, parser, metadata)
    if not parsed:
        return None

    if supplier_name:
        parsed.supplier_name = supplier_name

    quote = _parsed_to_quote(session, parsed, project, "pdf" if lower_path.endswith(".pdf") else "excel", file_path)
    session.commit()
    return quote
