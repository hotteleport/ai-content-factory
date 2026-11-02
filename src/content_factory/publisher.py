"""Send drafts through a Telegram user session.

Bots cannot send Premium custom emoji, so drafts go out through Telethon.
"""

import json
from pathlib import Path
from typing import Optional

from telethon.sync import TelegramClient
from telethon.tl.types import MessageEntityBold, MessageEntityCustomEmoji, MessageEntityTextUrl

from .formatting import Rendered, Span, render


def to_telethon_entity(span: Span):
    if span.kind == "bold":
        return MessageEntityBold(span.offset, span.length)
    if span.kind == "url":
        return MessageEntityTextUrl(span.offset, span.length, span.value)
    if span.kind == "custom_emoji":
        return MessageEntityCustomEmoji(span.offset, span.length, int(span.value))
    raise ValueError(f"Unknown span kind: {span.kind}")


def load_emoji_map(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


class TelethonPublisher:
    def __init__(self, session_path: Path, api_id: int, api_hash: str, channel_id: int,
                 emoji_map: Optional[dict] = None):
        self._client = TelegramClient(str(session_path), api_id, api_hash)
        self._channel_id = channel_id
        self._emoji_map = emoji_map or {}
        self._connected = False

    def _connect(self) -> None:
        if self._connected:
            return
        self._client.connect()
        if not self._client.is_user_authorized():
            raise RuntimeError("Telegram session is not authorised. Run the login command first.")
        # Fills Telethon's entity cache, so the private channel can be found by its ID.
        self._client.get_dialogs()
        self._connected = True

    def send(self, markup: str) -> None:
        self._connect()
        rendered: Rendered = render(markup, self._emoji_map)
        self._client.send_message(
            self._channel_id,
            rendered.text,
            formatting_entities=[to_telethon_entity(span) for span in rendered.spans],
            link_preview=False,
        )
