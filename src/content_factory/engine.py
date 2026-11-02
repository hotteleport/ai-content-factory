"""The watcher loop: Telegram updates in, reviewed drafts out."""

import logging
import time

from .state import EngineState, StateStore
from .tasks import parse_update
from .telegram_api import TelegramApiError

log = logging.getLogger(__name__)

QUEUED = "👀"
DONE = "👍"
FAILED = "😢"
MAX_BACKOFF_SECONDS = 60


class Engine:
    def __init__(self, api, agent, publisher, store: StateStore, ideas_channel_id: int,
                 drafts_channel_id: int, poll_timeout: int = 5):
        self._api = api
        self._agent = agent
        self._publisher = publisher
        self._store = store
        self._ideas = ideas_channel_id
        self._drafts = drafts_channel_id
        self._poll_timeout = poll_timeout
        self._run = None
        self.state: EngineState = store.load()
        self.running = True

    def _react(self, task, emoji: str) -> None:
        # A reaction is only a status signal, so failing to set one must not lose work.
        try:
            self._api.set_reaction(task.chat_id, task.message_id, emoji)
        except TelegramApiError as exc:
            log.warning("Could not set reaction: %s", exc)

    def poll_updates(self) -> None:
        updates = self._api.get_updates(self.state.offset, self._poll_timeout)
        if not updates:
            return
        new_tasks = []
        for update in updates:
            task = parse_update(update, self._ideas, self._drafts)
            if task:
                new_tasks.append(task)
            self.state.offset = update["update_id"] + 1
        self.state.queue.extend(new_tasks)
        # Saved before reacting, so a crash here cannot drop an accepted task.
        self._store.save(self.state)
        for task in new_tasks:
            log.info("Queued %s from message %s", task.kind, task.message_id)
            self._react(task, QUEUED)

    def advance(self) -> None:
        if self._run is None:
            if self.state.queue:
                self.state.active = self.state.queue.pop(0)
                self._store.save(self.state)
                try:
                    self._run = self._agent.start(self.state.active)
                except OSError as exc:
                    # Without this, a missing CLI would crash on the same task after every restart.
                    log.error("Could not start agent: %s", type(exc).__name__)
                    task, self.state.active = self.state.active, None
                    self._store.save(self.state)
                    self._react(task, FAILED)
            return

        result = self._run.poll()
        if result is None:
            return

        task = self.state.active
        succeeded = False
        if result.ok:
            try:
                self._publisher.send(result.text)
                succeeded = True
            except Exception as exc:  # A bad draft must not stop the engine.
                log.error("Could not publish draft for message %s: %s", task.message_id, type(exc).__name__)
        else:
            log.error("Agent failed on message %s: %s", task.message_id, result.error)

        self._run = None
        self.state.active = None
        self._store.save(self.state)
        self._react(task, DONE if succeeded else FAILED)

    def step(self) -> None:
        self.poll_updates()
        self.advance()

    def run_forever(self) -> None:
        log.info("Content engine started")
        backoff = 1
        while self.running:
            try:
                self.step()
                backoff = 1
            except TelegramApiError as exc:
                log.warning("%s; retrying in %s s", exc, backoff)
                try:
                    # Telegram being down must not stop a finished agent from being collected.
                    self.advance()
                except TelegramApiError:
                    pass
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
        log.info("Content engine stopped")
