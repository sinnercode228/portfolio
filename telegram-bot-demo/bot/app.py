"""Сборка Bot и Dispatcher. Отдельно от main.py, чтобы тесты собирали бота без сети."""

from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat

from bot import texts
from bot.config import Config
from bot.db import Database
from bot.handlers import create_routers
from bot.services import tasks

logger = logging.getLogger(__name__)


def create_bot(config: Config, *, session: BaseSession | None = None) -> Bot:
    return Bot(
        token=config.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )


def create_dispatcher(config: Config, db: Database, *, storage: BaseStorage | None = None) -> Dispatcher:
    # config и db попадают в workflow_data и доступны в хендлерах как аргументы.
    # SimpleEventIsolation: апдейты одного пользователя обрабатываются по очереди,
    # поэтому быстрые двойные нажатия не ломают анкету и не создают дублей.
    dp = Dispatcher(
        storage=storage or MemoryStorage(),
        events_isolation=SimpleEventIsolation(),
        config=config,
        db=db,
    )
    dp.include_routers(*create_routers())
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    return dp


def _commands(pairs: list[tuple[str, str]]) -> list[BotCommand]:
    return [BotCommand(command=cmd, description=desc) for cmd, desc in pairs]


async def on_startup(bot: Bot, config: Config) -> None:
    me = await bot.get_me()
    logger.info("Бот @%s (id=%s) запущен", me.username, me.id)

    await bot.set_my_commands(_commands(texts.USER_COMMANDS), scope=BotCommandScopeAllPrivateChats())
    for admin_id in config.admin_ids:
        try:
            await bot.set_my_commands(
                _commands(texts.USER_COMMANDS + texts.ADMIN_COMMANDS),
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except TelegramAPIError as exc:
            logger.warning(
                "Не удалось установить меню команд для админа %s (он уже писал боту /start?): %s",
                admin_id,
                exc,
            )

    if not config.admin_ids:
        logger.warning(
            "ADMIN_IDS не задан: заявки сохраняются в БД, но уведомления никому не приходят. "
            "Напишите боту /id и добавьте свой ID в .env"
        )


async def on_shutdown() -> None:
    logger.info("Бот останавливается…")
    # Сессия Telegram ещё открыта: даём идущей рассылке немного времени завершиться.
    await tasks.wait_all(grace_seconds=15)
