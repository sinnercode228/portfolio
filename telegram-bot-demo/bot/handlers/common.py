"""Общие команды: /start, /help, /cancel, /id и отслеживание блокировки бота."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import KICKED, MEMBER, ChatMemberUpdatedFilter, Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import ChatMemberUpdated, Message

from bot import keyboards as kb
from bot import texts
from bot.config import Config
from bot.db import Database
from bot.formatting import render_help, render_menu, render_start
from bot.states import BroadcastForm

logger = logging.getLogger(__name__)

_BROADCAST_STATES = frozenset(s.state for s in BroadcastForm.__all_states__)


async def cmd_start(message: Message, state: FSMContext, db: Database) -> None:
    user = message.from_user
    current = await state.get_state()
    if current is not None:  # /start посреди анкеты или рассылки = отмена
        await state.clear()
        text = texts.BROADCAST_CANCELLED if current in _BROADCAST_STATES else texts.LEAD_CANCELLED
        await message.answer(text, reply_markup=kb.remove_reply())
    if user is not None:
        await db.upsert_user(user.id, user.username, user.full_name)
    await message.answer(
        render_start(user.first_name if user else None),
        reply_markup=kb.main_menu(),
    )


async def cmd_help(message: Message, config: Config) -> None:
    user_id = message.from_user.id if message.from_user else None
    await message.answer(render_help(config.is_admin(user_id)))


async def cmd_id(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else "—"
    await message.answer(texts.MY_ID.format(user_id=user_id, chat_id=message.chat.id))


async def cancel_flow(bot: Bot, chat_id: int, state: FSMContext) -> None:
    """Сбрасывает любое состояние, убирает reply-клавиатуру и показывает меню."""
    current = await state.get_state()
    await state.clear()
    if current in _BROADCAST_STATES:
        await bot.send_message(chat_id, texts.BROADCAST_CANCELLED, reply_markup=kb.remove_reply())
        return
    await bot.send_message(chat_id, texts.LEAD_CANCELLED, reply_markup=kb.remove_reply())
    await bot.send_message(chat_id, render_menu(), reply_markup=kb.main_menu())


async def cmd_cancel(message: Message, state: FSMContext, bot: Bot) -> None:
    if await state.get_state() is None:
        await message.answer(texts.NOTHING_TO_CANCEL, reply_markup=kb.remove_reply())
        return
    await cancel_flow(bot, message.chat.id, state)


async def on_bot_blocked(event: ChatMemberUpdated, db: Database) -> None:
    await db.set_user_blocked(event.from_user.id, True)
    logger.info("Пользователь %s заблокировал бота", event.from_user.id)


async def on_bot_unblocked(event: ChatMemberUpdated, db: Database) -> None:
    user = event.from_user
    await db.upsert_user(user.id, user.username, user.full_name)
    logger.info("Пользователь %s снова активен", user.id)


def create_router() -> Router:
    router = Router(name="common")
    private = F.chat.type == ChatType.PRIVATE

    router.message.register(cmd_start, CommandStart(), private)
    router.message.register(cmd_help, Command("help"))
    router.message.register(cmd_id, Command("id"))
    router.message.register(cmd_cancel, Command("cancel"))
    # Слово «отмена» срабатывает только внутри анкеты/рассылки, чтобы не реагировать на обычную речь в группах.
    router.message.register(cmd_cancel, F.text.lower().in_(texts.CANCEL_WORDS), ~StateFilter(None))

    router.my_chat_member.register(on_bot_blocked, private, ChatMemberUpdatedFilter(member_status_changed=KICKED))
    router.my_chat_member.register(on_bot_unblocked, private, ChatMemberUpdatedFilter(member_status_changed=MEMBER))
    return router
