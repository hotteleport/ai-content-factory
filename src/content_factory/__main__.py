"""Command line entry point: run, login, export-posts."""

import argparse
import json
import logging
import signal

from dotenv import load_dotenv

from .agent import ClaudeAgent, PromptLibrary
from .config import load_settings
from .engine import Engine
from .state import StateStore
from .telegram_api import BotApi


def _run(settings) -> None:
    from .publisher import TelethonPublisher, load_emoji_map

    agent_dir = settings.data_dir / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    engine = Engine(
        api=BotApi(settings.bot_token),
        agent=ClaudeAgent(
            PromptLibrary(settings.prompts_dir), agent_dir, settings.agent_timeout_seconds, settings.model
        ),
        publisher=TelethonPublisher(
            settings.session_path, settings.api_id, settings.api_hash,
            settings.drafts_channel_id, load_emoji_map(settings.emoji_map_path),
        ),
        store=StateStore(settings.state_path),
        ideas_channel_id=settings.ideas_channel_id,
        drafts_channel_id=settings.drafts_channel_id,
        poll_timeout=settings.poll_timeout_seconds,
    )

    def stop(*_):
        engine.running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    engine.run_forever()


def _login(settings) -> None:
    from telethon.sync import TelegramClient

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    # Telethon asks for the phone, code and 2FA password in this terminal only.
    with TelegramClient(str(settings.session_path), settings.api_id, settings.api_hash) as client:
        me = client.get_me()
        print(f"Authorised. Premium account: {bool(me.premium)}")


def _export_posts(settings, channel: str, limit: int) -> None:
    from telethon.sync import TelegramClient
    from telethon.tl.types import MessageEntityCustomEmoji

    from .formatting import utf16_len

    posts = []
    emoji_map = {}
    with TelegramClient(str(settings.session_path), settings.api_id, settings.api_hash) as client:
        for message in client.iter_messages(channel, limit=limit):
            if not message.message:
                continue
            posts.append({
                "id": message.id,
                "date": message.date.isoformat(),
                "text": message.message,
                "views": message.views,
            })
            encoded = message.message.encode("utf-16-le")
            for entity in message.entities or []:
                if isinstance(entity, MessageEntityCustomEmoji):
                    start, end = entity.offset * 2, (entity.offset + entity.length) * 2
                    emoji_map[encoded[start:end].decode("utf-16-le")] = str(entity.document_id)

    (settings.data_dir / "reference_posts.json").write_text(
        json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    settings.emoji_map_path.write_text(json.dumps(emoji_map, ensure_ascii=False, indent=2), encoding="utf-8")
    characters = sum(utf16_len(post["text"]) for post in posts)
    print(f"Saved {len(posts)} posts ({characters} UTF-16 units) and {len(emoji_map)} custom emoji.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="content_factory")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", help="watch Telegram and write drafts")
    commands.add_parser("login", help="create the Telegram user session")
    export = commands.add_parser("export-posts", help="save your channel's posts for style analysis")
    export.add_argument("channel", help="public channel username, without @")
    export.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Stops HTTP client logs from printing request URLs, which contain the bot token.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    settings = load_settings()

    if args.command == "run":
        _run(settings)
    elif args.command == "login":
        _login(settings)
    else:
        _export_posts(settings, args.channel, args.limit)


if __name__ == "__main__":
    main()
