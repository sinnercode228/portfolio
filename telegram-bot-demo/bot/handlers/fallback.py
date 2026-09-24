"""Обработчики «по умолчанию» — для всего, что не подошло другим роутерам."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message

from bot import keyboards as kb
from bot import texts
from bot.handlers.utils import ack


async def unknown_message(message: Message) -> None:
    await message.answer(texts.UNKNOWN, reply_markup=kb.main_menu())


async def unknown_callback(callback: CallbackQuery) -> None:
    await ack(callback, texts.STALE_BUTTON)


def create_router() -> Router:
    router = Router(name="fallback")
    # Только личка: в админ-группе бот не должен отвечать на каждое сообщение.
    router.message.register(unknown_message, F.chat.type == ChatType.PRIVATE)
    router.callback_query.register(unknown_callback)
    return router
