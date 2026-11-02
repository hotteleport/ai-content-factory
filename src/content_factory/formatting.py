"""Convert agent output into plain text plus Telegram formatting spans.

Telegram measures entity offsets in UTF-16 code units, while Python indexes by
code point. An emoji outside the Basic Multilingual Plane is one Python
character but two UTF-16 units, so every offset here is converted explicitly.
"""

import re
from dataclasses import dataclass
from typing import Mapping, Optional

MAX_MESSAGE_UTF16 = 4096

_MARKUP = re.compile(
    r"\*\*(?P<bold>.+?)\*\*|\[(?P<label>[^\]\n]+)\]\((?P<url>https?://[^)\s]+)\)",
    re.DOTALL,
)


class MessageTooLong(ValueError):
    pass


@dataclass(frozen=True)
class Span:
    kind: str
    offset: int
    length: int
    value: Optional[str] = None


@dataclass(frozen=True)
class Rendered:
    text: str
    spans: tuple


def utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _emoji_spans(text: str, emoji_map: Mapping[str, str]) -> list:
    spans = []
    taken = set()
    # Longest first, so a compound emoji wins over the emoji it starts with.
    for char in sorted(emoji_map, key=len, reverse=True):
        start = text.find(char)
        while start != -1:
            positions = range(start, start + len(char))
            if not taken.intersection(positions):
                taken.update(positions)
                spans.append(
                    Span("custom_emoji", utf16_len(text[:start]), utf16_len(char), emoji_map[char])
                )
            start = text.find(char, start + len(char))
    return spans


def render(markup: str, emoji_map: Optional[Mapping[str, str]] = None) -> Rendered:
    """Parse **bold** and [label](url), then attach custom emoji."""
    parts = []
    spans = []
    position = 0
    plain_len = 0

    for match in _MARKUP.finditer(markup):
        before = markup[position:match.start()]
        parts.append(before)
        plain_len += utf16_len(before)

        content = match.group("bold") if match.group("bold") is not None else match.group("label")
        length = utf16_len(content)
        if match.group("bold") is not None:
            spans.append(Span("bold", plain_len, length))
        else:
            spans.append(Span("url", plain_len, length, match.group("url")))
        parts.append(content)
        plain_len += length
        position = match.end()

    parts.append(markup[position:])
    text = "".join(parts)

    if utf16_len(text) > MAX_MESSAGE_UTF16:
        raise MessageTooLong(f"{utf16_len(text)} UTF-16 units, limit is {MAX_MESSAGE_UTF16}")

    spans.extend(_emoji_spans(text, emoji_map or {}))
    spans.sort(key=lambda span: (span.offset, span.length))
    return Rendered(text, tuple(spans))
