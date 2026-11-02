import pytest
import requests

from content_factory.config import ConfigError, load_settings
from content_factory.telegram_api import BotApi, TelegramApiError

TOKEN = "123:SECRET"


class BrokenSession:
    def post(self, url, json, timeout):
        raise requests.ConnectionError(f"could not reach {url}")


class Response:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class RecordingSession:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append((url, json))
        return Response(self.data)


def test_network_error_never_exposes_the_token():
    with pytest.raises(TelegramApiError) as caught:
        BotApi(TOKEN, BrokenSession()).get_updates(None, 5)
    assert "SECRET" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_get_updates_only_asks_for_channel_posts():
    session = RecordingSession({"ok": True, "result": []})
    BotApi(TOKEN, session).get_updates(5, 5)
    assert session.calls[0][1] == {"timeout": 5, "allowed_updates": ["channel_post"], "offset": 5}


def test_api_error_is_raised():
    session = RecordingSession({"ok": False, "description": "Unauthorized"})
    with pytest.raises(TelegramApiError, match="Unauthorized"):
        BotApi(TOKEN, session).get_updates(None, 5)


def env(**overrides):
    values = {
        "TELEGRAM_BOT_TOKEN": "t",
        "TELEGRAM_API_ID": "1",
        "TELEGRAM_API_HASH": "h",
        "IDEAS_CHANNEL_ID": "-100",
        "DRAFTS_CHANNEL_ID": "-200",
    }
    values.update(overrides)
    return values


def test_settings_load_from_environment():
    settings = load_settings(env())
    assert (settings.api_id, settings.ideas_channel_id, settings.model) == (1, -100, None)


def test_missing_setting_is_named_without_showing_values():
    with pytest.raises(ConfigError, match="TELEGRAM_BOT_TOKEN"):
        load_settings(env(TELEGRAM_BOT_TOKEN=""))


def test_channel_id_must_be_a_number():
    with pytest.raises(ConfigError, match="IDEAS_CHANNEL_ID"):
        load_settings(env(IDEAS_CHANNEL_ID="ideas"))
