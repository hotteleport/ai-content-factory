"""Settings, read from the environment so no secret lives in the code."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    bot_token: str
    api_id: int
    api_hash: str
    ideas_channel_id: int
    drafts_channel_id: int
    data_dir: Path
    model: Optional[str] = None
    agent_timeout_seconds: int = 600
    poll_timeout_seconds: int = 5

    @property
    def session_path(self) -> Path:
        return self.data_dir / "telegram"

    @property
    def state_path(self) -> Path:
        return self.data_dir / "engine_state.json"

    @property
    def prompts_dir(self) -> Path:
        return self.data_dir / "prompts"

    @property
    def emoji_map_path(self) -> Path:
        return self.data_dir / "custom_emoji_map.json"


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required setting: {name}")
    return value


def _required_int(env: Mapping[str, str], name: str) -> int:
    value = _required(env, name)
    try:
        return int(value)
    except ValueError:
        raise ConfigError(f"{name} must be a whole number") from None


def load_settings(env: Mapping[str, str] = os.environ) -> Settings:
    return Settings(
        bot_token=_required(env, "TELEGRAM_BOT_TOKEN"),
        api_id=_required_int(env, "TELEGRAM_API_ID"),
        api_hash=_required(env, "TELEGRAM_API_HASH"),
        ideas_channel_id=_required_int(env, "IDEAS_CHANNEL_ID"),
        drafts_channel_id=_required_int(env, "DRAFTS_CHANNEL_ID"),
        data_dir=Path(env.get("FACTORY_DATA_DIR", "private")).expanduser().resolve(),
        model=env.get("CLAUDE_MODEL", "").strip() or None,
    )
