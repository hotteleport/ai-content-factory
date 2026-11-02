import pytest

from content_factory.agent import AgentResult
from content_factory.engine import DONE, FAILED, QUEUED, Engine
from content_factory.state import StateStore
from content_factory.tasks import IDEA, Task
from content_factory.telegram_api import TelegramApiError

IDEAS = -100
DRAFTS = -200


class FakeApi:
    def __init__(self):
        self.batches = []
        self.reactions = []
        self.offsets = []
        self.reaction_error = False

    def get_updates(self, offset, timeout):
        self.offsets.append(offset)
        return self.batches.pop(0) if self.batches else []

    def set_reaction(self, chat_id, message_id, emoji):
        if self.reaction_error:
            raise TelegramApiError("setMessageReaction failed")
        self.reactions.append((message_id, emoji))


class FakeRun:
    def __init__(self, result):
        self.result = result

    def poll(self):
        return self.result


class FakeAgent:
    def __init__(self):
        self.started = []
        self.result = AgentResult(True, text="A draft")

    def start(self, task):
        self.started.append(task)
        return FakeRun(self.result)


class FakePublisher:
    def __init__(self):
        self.sent = []
        self.error = None

    def send(self, text):
        if self.error:
            raise self.error
        self.sent.append(text)


def idea_update(update_id, message_id, chat_id=IDEAS):
    return {
        "update_id": update_id,
        "channel_post": {"message_id": message_id, "chat": {"id": chat_id}, "text": f"Idea {message_id}"},
    }


@pytest.fixture
def parts(tmp_path):
    return FakeApi(), FakeAgent(), FakePublisher(), StateStore(tmp_path / "state.json")


def make_engine(parts):
    api, agent, publisher, store = parts
    return Engine(api, agent, publisher, store, IDEAS, DRAFTS)


def test_idea_runs_from_queue_to_published_draft(parts):
    api, agent, publisher, _ = parts
    engine = make_engine(parts)
    api.batches.append([idea_update(10, 1)])

    engine.step()
    assert api.reactions == [(1, QUEUED)]
    assert agent.started[0].text == "Idea 1"

    engine.step()
    assert publisher.sent == ["A draft"]
    assert api.reactions[-1] == (1, DONE)
    assert engine.state.active is None


def test_offset_moves_past_handled_updates(parts):
    api, *_ = parts
    engine = make_engine(parts)
    api.batches.append([idea_update(10, 1), idea_update(11, 2, chat_id=-999)])
    engine.poll_updates()
    engine.poll_updates()
    assert api.offsets == [None, 12]


def test_ideas_run_one_at_a_time_in_order(parts):
    api, agent, *_ = parts
    engine = make_engine(parts)
    api.batches.append([idea_update(10, 1), idea_update(11, 2)])

    engine.step()
    assert [task.message_id for task in agent.started] == [1]
    engine.step()
    engine.step()
    assert [task.message_id for task in agent.started] == [1, 2]


def test_agent_failure_reacts_and_publishes_nothing(parts):
    api, agent, publisher, _ = parts
    agent.result = AgentResult(False, error="boom")
    engine = make_engine(parts)
    api.batches.append([idea_update(10, 1)])
    engine.step()
    engine.step()
    assert publisher.sent == []
    assert api.reactions[-1] == (1, FAILED)


def test_publish_failure_reacts_and_engine_continues(parts):
    api, _, publisher, _ = parts
    publisher.error = ValueError("too long")
    engine = make_engine(parts)
    api.batches.append([idea_update(10, 1)])
    engine.step()
    engine.step()
    assert api.reactions[-1] == (1, FAILED)
    assert engine.state.active is None


def test_reaction_failure_does_not_lose_the_task(parts):
    api, agent, *_ = parts
    api.reaction_error = True
    engine = make_engine(parts)
    api.batches.append([idea_update(10, 1)])
    engine.step()
    assert agent.started[0].message_id == 1


def test_agent_that_cannot_start_fails_only_that_task(parts):
    api, agent, *_ = parts

    def missing_cli(task):
        raise FileNotFoundError("claude")

    agent.start = missing_cli
    engine = make_engine(parts)
    api.batches.append([idea_update(10, 1)])
    engine.step()
    assert api.reactions[-1] == (1, FAILED)
    assert engine.state.active is None
    assert make_engine(parts).state.queue == []


def test_restart_recovers_queue_and_interrupted_task(parts):
    api, agent, _, store = parts
    engine = make_engine(parts)
    api.batches.append([idea_update(10, 1), idea_update(11, 2)])
    engine.step()

    restarted = make_engine(parts)
    assert [task.message_id for task in restarted.state.queue] == [1, 2]
    assert restarted.state.offset == 12


def test_state_round_trip_keeps_non_ascii_text(tmp_path):
    store = StateStore(tmp_path / "state.json")
    state = store.load()
    state.queue.append(Task(IDEA, 1, 1, "Идея 🚀"))
    store.save(state)
    assert store.load().queue[0].text == "Идея 🚀"
