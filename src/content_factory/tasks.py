"""Turn raw Telegram updates into work items."""

from dataclasses import asdict, dataclass
from typing import Optional

IDEA = "idea"
REVISION = "revision"


@dataclass(frozen=True)
class Task:
    kind: str
    chat_id: int
    message_id: int
    text: str
    original: Optional[str] = None
    quote: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        return cls(**data)


def _body(message: dict) -> str:
    return (message.get("text") or message.get("caption") or "").strip()


def parse_update(update: dict, ideas_channel_id: int, drafts_channel_id: int) -> Optional[Task]:
    """Return a task for an allowed channel, or None for anything else."""
    post = update.get("channel_post")
    if not post:
        return None

    chat_id = post.get("chat", {}).get("id")
    text = _body(post)
    if not text:
        return None

    if chat_id == ideas_channel_id:
        return Task(IDEA, chat_id, post["message_id"], text)

    if chat_id == drafts_channel_id:
        # Drafts sent by the agent are not replies, so they never trigger a new run.
        parent = post.get("reply_to_message")
        if not parent:
            return None
        return Task(
            REVISION,
            chat_id,
            post["message_id"],
            text,
            original=_body(parent),
            quote=(post.get("quote") or {}).get("text"),
        )

    return None
