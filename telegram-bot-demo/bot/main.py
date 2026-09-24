"""Точка входа: ``python -m bot``."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import sys

from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError

from bot.app import create_bot, create_dispatcher
from bot.config import Config, ConfigError, load_config, setup_logging
from bot.db import Database

logger = logging.getLogger("bot")


async def run_bot(config: Config) -> None:
    db = Database(config.db_path)
    try:
        await db.connect()
    except (OSError, sqlite3.Error) as exc:
        await db.close()
        raise ConfigError(f"DB_PATH: не удалось открыть базу «{config.db_path}»: {exc}") from exc
    bot = create_bot(config)
    dp = create_dispatcher(config, db)
    try:
        # SIGINT/SIGTERM обрабатываются aiogram: текущие апдейты дорабатывают, затем выход.
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        # aiogram закрывает сессию сам, но не если упал ещё on_startup (например, неверный токен)
        await bot.session.close()
        await db.close()


def main() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 2

    try:
        setup_logging(config.log_level, config.log_file)
    except OSError as exc:
        print(f"Ошибка конфигурации: LOG_FILE: не удалось открыть «{config.log_file}»: {exc}", file=sys.stderr)
        return 2
    logger.info("Конфигурация загружена: %r", config)  # токен скрыт (repr=False)

    try:
        asyncio.run(run_bot(config))
    except ConfigError as exc:
        logger.critical("Ошибка конфигурации: %s", exc)
        return 2
    except TelegramUnauthorizedError:
        logger.critical("Telegram отклонил BOT_TOKEN (Unauthorized). Проверьте токен в .env")
        return 1
    except TelegramNetworkError as exc:
        logger.critical("Нет связи с api.telegram.org: %s", exc)
        return 1
    except KeyboardInterrupt:
        logger.info("Остановлено пользователем")
    return 0
