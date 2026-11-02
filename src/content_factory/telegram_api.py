"""Minimal Telegram Bot API client used to watch channels."""

from typing import Optional

import requests


class TelegramApiError(RuntimeError):
    pass


class BotApi:
    def __init__(self, token: str, session: Optional[requests.Session] = None):
        self._base = f"https://api.telegram.org/bot{token}"
        self._session = session or requests.Session()

    def _call(self, method: str, payload: dict, timeout: float):
        try:
            response = self._session.post(f"{self._base}/{method}", json=payload, timeout=timeout)
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            # The request URL contains the bot token, so the original message must not be logged.
            raise TelegramApiError(f"{method} failed: {type(exc).__name__}") from None
        if not data.get("ok"):
            raise TelegramApiError(f"{method} failed: {data.get('description', 'unknown error')}")
        return data["result"]

    def get_updates(self, offset: Optional[int], timeout: int) -> list:
        payload = {"timeout": timeout, "allowed_updates": ["channel_post"]}
        if offset is not None:
            payload["offset"] = offset
        return self._call("getUpdates", payload, timeout=timeout + 10)

    def set_reaction(self, chat_id: int, message_id: int, emoji: str) -> None:
        self._call(
            "setMessageReaction",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "reaction": [{"type": "emoji", "emoji": emoji}],
            },
            timeout=15,
        )
