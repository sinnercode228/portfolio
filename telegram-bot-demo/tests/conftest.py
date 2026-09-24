from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import Chat, User

from bot.app import create_bot, create_dispatcher
from bot.config import Config
from bot.db import Database
from bot.services import broadcast
from tests.fakes import FakeSession, TgClient

FAKE_TOKEN = "123456789:AAFakeTokenForTestsOnly_abcdefghijk"
ADMIN_ID = 111
ADMIN_GROUP_ID = -100222
CLIENT_ID = 555


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        bot_token=FAKE_TOKEN,
        admin_ids=frozenset({ADMIN_ID}),
        admin_chat_ids=(ADMIN_ID, ADMIN_GROUP_ID),
        db_path=tmp_path / "test.db",
        tz_name="Europe/Moscow",
        lead_cooldown_minutes=0,
    )


@pytest.fixture
async def db(config: Config) -> AsyncIterator[Database]:
    database = Database(config.db_path)
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def bot(config: Config, session: FakeSession) -> Bot:
    return create_bot(config, session=session)


@pytest.fixture
def dp(config: Config, db: Database, monkeypatch: pytest.MonkeyPatch) -> Dispatcher:
    monkeypatch.setattr(broadcast, "SEND_DELAY_SECONDS", 0)
    return create_dispatcher(config, db)


@pytest.fixture
def client(dp: Dispatcher, bot: Bot) -> TgClient:
    user = User(id=CLIENT_ID, is_bot=False, first_name="Анна", last_name="Смирнова", username="anna_demo")
    return TgClient(dp, bot, user)


@pytest.fixture
def admin(dp: Dispatcher, bot: Bot) -> TgClient:
    user = User(id=ADMIN_ID, is_bot=False, first_name="Админ", username="admin_demo")
    return TgClient(dp, bot, user)


@pytest.fixture
def admin_in_group(dp: Dispatcher, bot: Bot) -> TgClient:
    user = User(id=ADMIN_ID, is_bot=False, first_name="Админ")
    return TgClient(dp, bot, user, chat=Chat(id=ADMIN_GROUP_ID, type="supergroup", title="Заявки"))
