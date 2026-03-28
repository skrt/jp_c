"""Group emails into projects based on thread, subject patterns, and similarity."""

import re
from collections import defaultdict
from difflib import SequenceMatcher

from quote_manager.gmail.fetcher import RawEmail


# Common patterns for quote/RFQ identifiers in subjects
RFQ_PATTERNS = [
    re.compile(r"RFQ[-\s]?(\d+[-\w]*)", re.IGNORECASE),
    re.compile(r"見積[-\s]?(?:番号|No\.?)[-\s]?(\S+)"),
    re.compile(r"Quote[-\s]?#?(\d+[-\w]*)", re.IGNORECASE),
    re.compile(r"案件[-\s]?(?:番号|No\.?)[-\s]?(\S+)"),
    re.compile(r"\[(.+?)\]"),  # Bracketed identifiers like [ProjectA]
]

# Prefixes to strip for subject normalization
REPLY_PREFIXES = re.compile(r"^(Re:|RE:|Fwd:|FW:|転送:|返信:)\s*", re.IGNORECASE)

SUBJECT_SIMILARITY_THRESHOLD = 0.7


def extract_project_key(subject: str) -> str | None:
    """Extract a project identifier from an email subject."""
    for pattern in RFQ_PATTERNS:
        match = pattern.search(subject)
        if match:
            return match.group(1).strip()
    return None


def _normalize_subject(subject: str) -> str:
    """Strip Re:/Fwd: prefixes and normalize whitespace."""
    s = subject
    for _ in range(5):
        s_new = REPLY_PREFIXES.sub("", s).strip()
        if s_new == s:
            break
        s = s_new
    return re.sub(r"\s+", " ", s).strip()


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


def _merge_similar_groups(
    groups: dict[str, list[RawEmail]],
) -> dict[str, list[RawEmail]]:
    """Merge groups whose subject-based keys are similar enough."""
    keys = list(groups.keys())
    merged: dict[str, list[RawEmail]] = {}
    used = set()

    for i, k1 in enumerate(keys):
        if k1 in used:
            continue
        merged_emails = list(groups[k1])
        canonical_key = k1

        for j in range(i + 1, len(keys)):
            k2 = keys[j]
            if k2 in used:
                continue

            # Compare normalized subjects from first email in each group
            subj1 = _normalize_subject(groups[k1][0].subject)
            subj2 = _normalize_subject(groups[k2][0].subject)
            sim = SequenceMatcher(None, subj1, subj2).ratio()

            if sim >= SUBJECT_SIMILARITY_THRESHOLD:
                merged_emails.extend(groups[k2])
                used.add(k2)

        merged[canonical_key] = merged_emails
        used.add(k1)

    return merged


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

    # Second pass: merge similar groups
    result = _merge_similar_groups(result)

    return result


def suggest_project_name(emails: list[RawEmail]) -> str:
    """Suggest a project name from a group of emails.

    Uses the most common normalized subject, stripped of Re:/Fwd: prefixes.
    """
    subjects = [_normalize_subject(e.subject) for e in emails]

    # Pick the shortest subject as it's likely the original (before Re:/Fwd:)
    if subjects:
        return min(subjects, key=len)
    return "不明な案件"


def summarize_group(key: str, emails: list[RawEmail]) -> dict:
    """Create a summary dict for a group of emails."""
    senders = list({e.sender_email for e in emails if e.sender_email})
    subjects = list({_normalize_subject(e.subject) for e in emails})
    dates = sorted([e.date for e in emails])
    has_attachments = any(e.attachment_paths for e in emails)

    return {
        "key": key,
        "suggested_name": suggest_project_name(emails),
        "email_count": len(emails),
        "senders": senders,
        "subjects": subjects,
        "date_range": (dates[0], dates[-1]) if dates else (None, None),
        "has_attachments": has_attachments,
        "emails": emails,
    }
