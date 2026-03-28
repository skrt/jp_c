"""Fetch emails and attachments from Gmail."""

import base64
import email.utils
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from quote_manager.config import get_settings
from quote_manager.gmail.auth import get_gmail_service


@dataclass
class RawEmail:
    """Raw email data fetched from Gmail."""
    message_id: str
    thread_id: str
    subject: str
    sender: str
    sender_email: str
    date: datetime
    body_text: str
    body_html: str
    attachment_paths: list[str] = field(default_factory=list)


def _extract_email_address(sender: str) -> str:
    """Extract email address from a sender string like 'Name <email@example.com>'."""
    _, addr = email.utils.parseaddr(sender)
    return addr


def _decode_body(payload: dict, mime_type: str) -> str:
    """Recursively search payload for body content of given MIME type."""
    if payload.get("mimeType") == mime_type:
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        result = _decode_body(part, mime_type)
        if result:
            return result
    return ""


def _download_attachments(service, message_id: str, payload: dict, save_dir: Path) -> list[str]:
    """Download all attachments from a message and return file paths."""
    paths = []
    for part in payload.get("parts", []):
        filename = part.get("filename")
        if not filename:
            # Check nested parts
            paths.extend(_download_attachments(service, message_id, part, save_dir))
            continue

        body = part.get("body", {})
        attachment_id = body.get("attachmentId")
        if not attachment_id:
            continue

        # Only download PDF, Excel, CSV files
        lower_name = filename.lower()
        if not any(lower_name.endswith(ext) for ext in (".pdf", ".xlsx", ".xls", ".csv")):
            continue

        att = (
            service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute()
        )
        data = base64.urlsafe_b64decode(att["data"])

        save_dir.mkdir(parents=True, exist_ok=True)
        file_path = save_dir / filename
        file_path.write_bytes(data)
        paths.append(str(file_path))

    return paths


def fetch_emails(query: str, max_results: int = 50) -> list[RawEmail]:
    """Fetch emails matching a Gmail search query.

    Args:
        query: Gmail search query (e.g., 'subject:見積 from:supplier@example.com').
        max_results: Maximum number of emails to fetch.

    Returns:
        List of RawEmail objects with body text and downloaded attachments.
    """
    settings = get_settings()
    service = get_gmail_service(settings.gmail_credentials_path, settings.gmail_token_path)

    results = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )

    messages = results.get("messages", [])
    emails = []

    for msg_ref in messages:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=msg_ref["id"], format="full")
            .execute()
        )

        headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
        subject = headers.get("subject", "(no subject)")
        sender = headers.get("from", "")
        date_str = headers.get("date", "")

        try:
            parsed_date = email.utils.parsedate_to_datetime(date_str)
        except (ValueError, TypeError):
            parsed_date = datetime.utcnow()

        payload = msg["payload"]
        body_text = _decode_body(payload, "text/plain")
        body_html = _decode_body(payload, "text/html")

        # Download attachments
        att_dir = settings.attachments_dir / str(msg_ref["id"])
        attachment_paths = _download_attachments(service, msg_ref["id"], payload, att_dir)

        emails.append(
            RawEmail(
                message_id=msg_ref["id"],
                thread_id=msg.get("threadId", ""),
                subject=subject,
                sender=sender,
                sender_email=_extract_email_address(sender),
                date=parsed_date,
                body_text=body_text,
                body_html=body_html,
                attachment_paths=attachment_paths,
            )
        )

    return emails
