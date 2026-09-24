"""Глобальный обработчик ошибок: логирует и вежливо сообщает пользователю."""

from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.types import ErrorEvent

from bot import texts

logger = logging.getLogger(__name__)


def _private_chat_id(event: ErrorEvent) -> int | None:
    """Личный чат, куда можно сообщить об ошибке. В группах (админ-чат) бот не шумит."""
    update = event.update
    message = update.message
    if message is None and update.callback_query is not None:
        message = update.callback_query.message
    if message is not None and message.chat.type == ChatType.PRIVATE:
        return message.chat.id
    return None


async def on_error(event: ErrorEvent, bot: Bot) -> bool:
    logger.error(
        "Ошибка при обработке update %s: %s",
        event.update.update_id,
        event.exception,
        exc_info=event.exception,
    )
    chat_id = _private_chat_id(event)
    if chat_id is not None:
        try:
            await bot.send_message(chat_id, texts.ERROR_GENERIC)
        except Exception:  # сообщение об ошибке не должно порождать новую
            logger.warning("Не удалось сообщить пользователю %s об ошибке", chat_id, exc_info=True)
    return True


def create_router() -> Router:
    router = Router(name="errors")
    router.errors.register(on_error)
    return router
