"""Вспомогательные функции для хендлеров."""

from __future__ import annotations

import contextlib
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

logger = logging.getLogger(__name__)


async def ack(callback: CallbackQuery, text: str | None = None, *, show_alert: bool = False) -> None:
    """Отвечает на нажатие кнопки (убирает «часики»), не прерывая хендлер при ошибке.

    Если бот был выключен, нажатия копятся у Telegram и после запуска приходят «протухшими»:
    ``answerCallbackQuery`` отвечает «query is too old». Само действие при этом нужно выполнить.
    """
    try:
        await callback.answer(text, show_alert=show_alert)
    except TelegramBadRequest as exc:
        logger.debug("Не удалось ответить на callback %s: %s", callback.id, exc)


def callback_chat_id(callback: CallbackQuery) -> int:
    """ID чата, где нажата кнопка (или личка пользователя, если сообщение недоступно)."""
    if callback.message is not None:
        return callback.message.chat.id
    return callback.from_user.id


async def safe_edit(
    callback: CallbackQuery,
    bot: Bot,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Редактирует сообщение с кнопкой; если это невозможно — отправляет новое.

    Ошибку «message is not modified» (повторное нажатие той же кнопки) молча игнорирует.
    """
    message = callback.message
    if isinstance(message, Message):
        try:
            await message.edit_text(text, reply_markup=reply_markup)
            return
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc):
                return
            logger.debug("Не удалось отредактировать сообщение, отправляю новое: %s", exc)
    await bot.send_message(callback_chat_id(callback), text, reply_markup=reply_markup)


async def drop_keyboard(callback: CallbackQuery) -> None:
    """Убирает inline-кнопки у сообщения, на котором нажали кнопку (ошибки игнорируются)."""
    if isinstance(callback.message, Message):
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_reply_markup(reply_markup=None)
