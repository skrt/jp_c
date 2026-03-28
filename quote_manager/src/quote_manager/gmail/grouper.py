"""Group emails into projects based on thread and subject patterns."""

import re
from collections import defaultdict

from quote_manager.gmail.fetcher import RawEmail


# Common patterns for quote/RFQ identifiers in subjects
RFQ_PATTERNS = [
    re.compile(r"RFQ[-\s]?(\d+[-\w]*)", re.IGNORECASE),
    re.compile(r"見積[-\s]?(?:番号|No\.?)[-\s]?(\S+)"),
    re.compile(r"Quote[-\s]?#?(\d+[-\w]*)", re.IGNORECASE),
    re.compile(r"案件[-\s]?(?:番号|No\.?)[-\s]?(\S+)"),
    re.compile(r"\[(.+?)\]"),  # Bracketed identifiers like [ProjectA]
]


def extract_project_key(subject: str) -> str | None:
    """Extract a project identifier from an email subject."""
    for pattern in RFQ_PATTERNS:
        match = pattern.search(subject)
        if match:
            return match.group(1).strip()
    return None


def group_by_thread(emails: list[RawEmail]) -> dict[str, list[RawEmail]]:
    """Group emails by Gmail thread ID."""
    groups: dict[str, list[RawEmail]] = defaultdict(list)
    for email in emails:
        groups[email.thread_id].append(email)
    return dict(groups)


def group_by_subject(emails: list[RawEmail]) -> dict[str, list[RawEmail]]:
    """Group emails by extracted project key from subject line."""
    groups: dict[str, list[RawEmail]] = defaultdict(list)
    ungrouped: list[RawEmail] = []

    for email in emails:
        key = extract_project_key(email.subject)
        if key:
            groups[key].append(email)
        else:
            ungrouped.append(email)

    if ungrouped:
        groups["_ungrouped"] = ungrouped

    return dict(groups)


def auto_group(emails: list[RawEmail]) -> dict[str, list[RawEmail]]:
    """Auto-group emails using thread ID first, then subject patterns.

    Returns a dict of group_key -> list of emails.
    Thread-based groups use 'thread:{thread_id}' as key.
    Subject-based groups use the extracted project key.
    """
    # First pass: group by thread
    thread_groups = group_by_thread(emails)

    # For each thread group, try to extract a better project key
    result: dict[str, list[RawEmail]] = {}
    for thread_id, thread_emails in thread_groups.items():
        # Try to find a project key from any email in the thread
        project_key = None
        for e in thread_emails:
            project_key = extract_project_key(e.subject)
            if project_key:
                break

        key = project_key or f"thread:{thread_id}"
        if key in result:
            result[key].extend(thread_emails)
        else:
            result[key] = thread_emails

    return result
