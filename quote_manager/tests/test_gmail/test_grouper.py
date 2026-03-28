"""Tests for email grouping logic."""

from datetime import datetime

from quote_manager.gmail.fetcher import RawEmail
from quote_manager.gmail.grouper import (
    extract_project_key,
    auto_group,
    suggest_project_name,
    summarize_group,
    _normalize_subject,
)


def _make_email(
    message_id: str = "msg1",
    thread_id: str = "thread1",
    subject: str = "見積書",
    sender: str = "test@example.com",
    **kwargs,
) -> RawEmail:
    return RawEmail(
        message_id=message_id,
        thread_id=thread_id,
        subject=subject,
        sender=sender,
        sender_email=sender,
        date=kwargs.get("date", datetime(2026, 3, 15)),
        body_text=kwargs.get("body_text", ""),
        body_html="",
        attachment_paths=kwargs.get("attachment_paths", []),
    )


class TestExtractProjectKey:
    def test_rfq_pattern(self):
        assert extract_project_key("RFQ-2026-042 見積依頼") == "2026-042"

    def test_quote_number(self):
        assert extract_project_key("見積番号 Q-001 の件") == "Q-001"

    def test_bracket_pattern(self):
        assert extract_project_key("[サーバー調達] 見積のお願い") == "サーバー調達"

    def test_no_match(self):
        assert extract_project_key("お世話になっております") is None

    def test_case_number(self):
        assert extract_project_key("案件番号 A-123 見積回答") == "A-123"


class TestNormalizeSubject:
    def test_strip_re(self):
        assert _normalize_subject("Re: 見積のお願い") == "見積のお願い"

    def test_strip_nested_re_fwd(self):
        assert _normalize_subject("Re: Fwd: Re: 見積書") == "見積書"

    def test_strip_japanese_prefixes(self):
        assert _normalize_subject("返信: 転送: 見積") == "見積"

    def test_no_prefix(self):
        assert _normalize_subject("見積のお願い") == "見積のお願い"


class TestAutoGroup:
    def test_group_by_thread(self):
        """Same thread ID -> same group."""
        emails = [
            _make_email("m1", "t1", "見積のお願い", "a@x.com"),
            _make_email("m2", "t1", "Re: 見積のお願い", "b@x.com"),
            _make_email("m3", "t2", "別件の見積", "c@x.com"),
        ]
        groups = auto_group(emails)
        assert len(groups) == 2

    def test_extract_key_from_thread(self):
        """Thread with RFQ number uses that as key."""
        emails = [
            _make_email("m1", "t1", "RFQ-001 見積依頼", "a@x.com"),
            _make_email("m2", "t1", "Re: RFQ-001 見積依頼", "b@x.com"),
        ]
        groups = auto_group(emails)
        assert "001" in list(groups.keys())[0]

    def test_single_email_group(self):
        emails = [_make_email("m1", "t1", "見積", "a@x.com")]
        groups = auto_group(emails)
        assert len(groups) == 1


class TestSuggestProjectName:
    def test_picks_shortest(self):
        emails = [
            _make_email(subject="Re: Re: サーバー見積"),
            _make_email(subject="Re: サーバー見積"),
            _make_email(subject="サーバー見積"),
        ]
        name = suggest_project_name(emails)
        assert name == "サーバー見積"


class TestSummarizeGroup:
    def test_summary_fields(self):
        emails = [
            _make_email("m1", "t1", "見積", "a@x.com",
                        date=datetime(2026, 3, 10),
                        attachment_paths=["/tmp/a.pdf"]),
            _make_email("m2", "t1", "Re: 見積", "b@x.com",
                        date=datetime(2026, 3, 15)),
        ]
        s = summarize_group("test_key", emails)

        assert s["key"] == "test_key"
        assert s["email_count"] == 2
        assert "a@x.com" in s["senders"]
        assert "b@x.com" in s["senders"]
        assert s["has_attachments"] is True
        assert s["date_range"][0] == datetime(2026, 3, 10)
        assert s["date_range"][1] == datetime(2026, 3, 15)
