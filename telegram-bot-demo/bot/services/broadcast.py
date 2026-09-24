"""Рассылка сообщения всем активным пользователям с учётом лимитов Telegram."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNotFound,
    TelegramRetryAfter,
)

from bot.db import Database

logger = logging.getLogger(__name__)

# Telegram разрешает ~30 сообщений в секунду; держим запас.
SEND_DELAY_SECONDS = 0.05


@dataclass(slots=True)
class BroadcastResult:
    total: int = 0
    sent: int = 0
    blocked: int = 0
    failed: int = 0


async def _copy_with_retry(bot: Bot, chat_id: int, from_chat_id: int, message_id: int) -> None:
    try:
        await bot.copy_message(chat_id=chat_id, from_chat_id=from_chat_id, message_id=message_id)
    except TelegramRetryAfter as exc:
        logger.warning("Флуд-лимит при рассылке, пауза %s с", exc.retry_after)
        await asyncio.sleep(exc.retry_after)
        await bot.copy_message(chat_id=chat_id, from_chat_id=from_chat_id, message_id=message_id)


async def run_broadcast(
    bot: Bot,
    db: Database,
    from_chat_id: int,
    message_id: int,
    *,
    delay: float | None = None,
) -> BroadcastResult:
    """Копирует сообщение (без пометки «Переслано») каждому активному пользователю.

    Пользователи, заблокировавшие бота, помечаются в БД и исключаются из следующих рассылок.
    """
    delay = SEND_DELAY_SECONDS if delay is None else delay
    user_ids = await db.get_active_user_ids()
    result = BroadcastResult(total=len(user_ids))
    logger.info("Рассылка: старт, получателей %s", result.total)

    for user_id in user_ids:
        try:
            await _copy_with_retry(bot, user_id, from_chat_id, message_id)
            result.sent += 1
        except (TelegramForbiddenError, TelegramNotFound):
            # бот заблокирован или аккаунт удалён
            result.blocked += 1
            await db.set_user_blocked(user_id, True)
        except TelegramBadRequest as exc:
            if "chat not found" in str(exc).lower():
                result.blocked += 1
                await db.set_user_blocked(user_id, True)
            else:
                result.failed += 1
                logger.warning("Рассылка: не доставлено пользователю %s: %s", user_id, exc)
        except TelegramAPIError as exc:
            result.failed += 1
            logger.warning("Рассылка: не доставлено пользователю %s: %s", user_id, exc)
        if delay:
            await asyncio.sleep(delay)

    logger.info(
        "Рассылка: готово — доставлено %s, заблокировали %s, ошибок %s",
        result.sent,
        result.blocked,
        result.failed,
    )
    return result
