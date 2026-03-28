"""Fetch messages and files from Slack channels."""

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from quote_manager.config import get_settings


@dataclass
class SlackMessage:
    """Raw message data fetched from Slack."""
    message_id: str  # channel_id + ts
    channel_id: str
    thread_ts: str | None
    sender: str
    sender_name: str
    text: str
    timestamp: datetime
    attachment_paths: list[str] = field(default_factory=list)


def _get_client() -> WebClient:
    settings = get_settings()
    if not settings.slack_bot_token:
        raise ValueError(
            "SLACK_BOT_TOKEN is not set. "
            "Create a Slack app and add the bot token to .env"
        )
    return WebClient(token=settings.slack_bot_token)


def _download_file(client: WebClient, file_info: dict, save_dir: Path) -> str | None:
    """Download a Slack file attachment if it's a supported type."""
    name = file_info.get("name", "unknown")
    lower_name = name.lower()

    if not any(lower_name.endswith(ext) for ext in (".pdf", ".xlsx", ".xls", ".csv")):
        return None

    url = file_info.get("url_private_download") or file_info.get("url_private")
    if not url:
        return None

    save_dir.mkdir(parents=True, exist_ok=True)
    file_path = save_dir / name

    import urllib.request
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {client.token}")
    with urllib.request.urlopen(req) as response:
        file_path.write_bytes(response.read())

    return str(file_path)


def _get_user_name(client: WebClient, user_id: str) -> str:
    """Look up a Slack user's display name."""
    try:
        result = client.users_info(user=user_id)
        profile = result["user"]["profile"]
        return profile.get("display_name") or profile.get("real_name") or user_id
    except SlackApiError:
        return user_id


def fetch_channel_messages(
    channel_id: str,
    keyword: str | None = None,
    oldest: datetime | None = None,
    limit: int = 100,
) -> list[SlackMessage]:
    """Fetch messages from a Slack channel, optionally filtered by keyword.

    Args:
        channel_id: Slack channel ID.
        keyword: Optional keyword to filter messages (e.g., '見積', 'quote').
        oldest: Only fetch messages after this timestamp.
        limit: Maximum number of messages to return.

    Returns:
        List of SlackMessage objects.
    """
    settings = get_settings()
    client = _get_client()

    kwargs = {"channel": channel_id, "limit": limit}
    if oldest:
        kwargs["oldest"] = str(oldest.timestamp())

    try:
        result = client.conversations_history(**kwargs)
    except SlackApiError as e:
        raise RuntimeError(f"Failed to fetch Slack messages: {e.response['error']}")

    messages = []
    user_cache: dict[str, str] = {}

    for msg in result.get("messages", []):
        text = msg.get("text", "")

        # Filter by keyword if specified
        if keyword and keyword.lower() not in text.lower():
            continue

        user_id = msg.get("user", "unknown")
        if user_id not in user_cache:
            user_cache[user_id] = _get_user_name(client, user_id)

        ts = msg.get("ts", "")
        try:
            msg_time = datetime.fromtimestamp(float(ts))
        except (ValueError, TypeError):
            msg_time = datetime.utcnow()

        # Download file attachments
        attachment_paths = []
        for file_info in msg.get("files", []):
            att_dir = settings.attachments_dir / f"slack_{channel_id}_{ts}"
            path = _download_file(client, file_info, att_dir)
            if path:
                attachment_paths.append(path)

        messages.append(
            SlackMessage(
                message_id=f"{channel_id}:{ts}",
                channel_id=channel_id,
                thread_ts=msg.get("thread_ts"),
                sender=user_id,
                sender_name=user_cache[user_id],
                text=text,
                timestamp=msg_time,
                attachment_paths=attachment_paths,
            )
        )

    return messages


def fetch_thread_messages(
    channel_id: str,
    thread_ts: str,
    limit: int = 100,
) -> list[SlackMessage]:
    """Fetch all messages in a Slack thread.

    Args:
        channel_id: Slack channel ID.
        thread_ts: Thread timestamp (parent message ts).
        limit: Maximum number of messages.

    Returns:
        List of SlackMessage objects in the thread.
    """
    settings = get_settings()
    client = _get_client()

    try:
        result = client.conversations_replies(
            channel=channel_id, ts=thread_ts, limit=limit
        )
    except SlackApiError as e:
        raise RuntimeError(f"Failed to fetch Slack thread: {e.response['error']}")

    messages = []
    user_cache: dict[str, str] = {}

    for msg in result.get("messages", []):
        user_id = msg.get("user", "unknown")
        if user_id not in user_cache:
            user_cache[user_id] = _get_user_name(client, user_id)

        ts = msg.get("ts", "")
        try:
            msg_time = datetime.fromtimestamp(float(ts))
        except (ValueError, TypeError):
            msg_time = datetime.utcnow()

        attachment_paths = []
        for file_info in msg.get("files", []):
            att_dir = settings.attachments_dir / f"slack_{channel_id}_{ts}"
            path = _download_file(client, file_info, att_dir)
            if path:
                attachment_paths.append(path)

        messages.append(
            SlackMessage(
                message_id=f"{channel_id}:{ts}",
                channel_id=channel_id,
                thread_ts=msg.get("thread_ts"),
                sender=user_id,
                sender_name=user_cache[user_id],
                text=msg.get("text", ""),
                timestamp=msg_time,
                attachment_paths=attachment_paths,
            )
        )

    return messages
