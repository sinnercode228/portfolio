from pathlib import Path

import pytest

from bot.config import ConfigError, load_config, parse_ids
from tests.conftest import FAKE_TOKEN


def test_load_config_full() -> None:
    config = load_config(
        {
            "BOT_TOKEN": FAKE_TOKEN,
            "ADMIN_IDS": "111, 222;222 333",
            "ADMIN_CHAT_IDS": "-100500",
            "DB_PATH": "/tmp/x.db",
            "TIMEZONE": "Asia/Yekaterinburg",
            "LOG_LEVEL": "debug",
            "LEAD_COOLDOWN_MINUTES": "0",
        }
    )
    assert config.admin_ids == frozenset({111, 222, 333})
    assert config.admin_chat_ids == (-100500,)
    assert config.db_path == Path("/tmp/x.db")
    assert config.tz_name == "Asia/Yekaterinburg"
    assert config.log_level == "DEBUG"
    assert config.lead_cooldown_minutes == 0
    assert config.is_admin(222) and not config.is_admin(999) and not config.is_admin(None)


def test_defaults_and_admin_chats_fallback_to_admin_ids() -> None:
    config = load_config({"BOT_TOKEN": FAKE_TOKEN, "ADMIN_IDS": "7,8"})
    assert config.admin_chat_ids == (7, 8)
    assert config.db_path == Path("data/leads.db")
    assert config.tz_name == "Europe/Moscow"
    assert config.lead_cooldown_minutes == 5


def test_token_is_hidden_in_repr() -> None:
    config = load_config({"BOT_TOKEN": FAKE_TOKEN})
    assert FAKE_TOKEN not in repr(config)


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({}, "BOT_TOKEN не задан"),
        ({"BOT_TOKEN": "123456789:replace-me-with-token-from-botfather"}, "BOT_TOKEN не задан"),
        ({"BOT_TOKEN": "not-a-token"}, "некорректно"),
        ({"BOT_TOKEN": FAKE_TOKEN, "ADMIN_IDS": "123,abc"}, "ADMIN_IDS"),
        ({"BOT_TOKEN": FAKE_TOKEN, "TIMEZONE": "Mars/Olympus"}, "TIMEZONE"),
        ({"BOT_TOKEN": FAKE_TOKEN, "LOG_LEVEL": "LOUD"}, "LOG_LEVEL"),
        ({"BOT_TOKEN": FAKE_TOKEN, "LEAD_COOLDOWN_MINUTES": "-1"}, "LEAD_COOLDOWN_MINUTES"),
        ({"BOT_TOKEN": FAKE_TOKEN, "LEAD_COOLDOWN_MINUTES": "five"}, "LEAD_COOLDOWN_MINUTES"),
    ],
)
def test_config_errors_are_human_readable(env: dict[str, str], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        load_config(env)


def test_parse_ids_empty() -> None:
    assert parse_ids(None, "X") == ()
    assert parse_ids("  ", "X") == ()
