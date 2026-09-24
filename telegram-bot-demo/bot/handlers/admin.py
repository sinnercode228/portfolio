"""Команды администратора: /leads, /export, /stats, /broadcast и статусы заявок."""

from __future__ import annotations

import logging
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.enums import ContentType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot import keyboards as kb
from bot import texts
from bot.callbacks import BroadcastCb, LeadStatusCb
from bot.config import Config
from bot.db import LEAD_STATUSES, Database
from bot.export import leads_to_csv
from bot.filters import IsAdmin
from bot.formatting import render_lead_card, render_leads_list, render_stats, status_title
from bot.handlers.utils import ack, callback_chat_id, drop_keyboard, safe_edit
from bot.services import tasks
from bot.services.broadcast import run_broadcast
from bot.states import BroadcastForm

logger = logging.getLogger(__name__)

LEADS_LIMIT = 10
BROADCAST_CONTENT_TYPES = frozenset(
    {
        ContentType.TEXT,
        ContentType.PHOTO,
        ContentType.VIDEO,
        ContentType.ANIMATION,
        ContentType.DOCUMENT,
        ContentType.AUDIO,
        ContentType.VOICE,
        ContentType.VIDEO_NOTE,
        ContentType.STICKER,
    }
)


async def cmd_leads(message: Message, db: Database, config: Config) -> None:
    leads = await db.get_last_leads(LEADS_LIMIT)
    await message.answer(render_leads_list(leads, config.tz))


async def cmd_export(message: Message, db: Database, config: Config) -> None:
    leads = await db.get_all_leads()
    if not leads:
        await message.answer(texts.LEADS_EMPTY)
        return
    payload = leads_to_csv(leads, config.tz)
    filename = f"leads_{datetime.now(config.tz):%Y-%m-%d_%H-%M}.csv"
    await message.answer_document(
        BufferedInputFile(payload, filename=filename),
        caption=texts.EXPORT_CAPTION.format(count=len(leads)),
    )
    logger.info("Админ %s выгрузил %s заявок", message.from_user.id if message.from_user else "?", len(leads))


async def cmd_stats(message: Message, db: Database, config: Config) -> None:
    stats = await db.get_stats(config.tz)
    await message.answer(render_stats(stats))


# -- рассылка -------------------------------------------------------------------------


async def cmd_broadcast(message: Message, state: FSMContext, db: Database) -> None:
    count = len(await db.get_active_user_ids())
    if not count:
        await message.answer(texts.BROADCAST_NO_RECIPIENTS)
        return
    await state.set_state(BroadcastForm.waiting_message)
    await message.answer(texts.BROADCAST_ASK.format(count=count))


async def broadcast_message_received(message: Message, state: FSMContext, db: Database) -> None:
    if message.content_type not in BROADCAST_CONTENT_TYPES:
        await message.answer(texts.BROADCAST_UNSUPPORTED)
        return
    await state.update_data(from_chat_id=message.chat.id, message_id=message.message_id)
    await state.set_state(BroadcastForm.confirm)
    count = len(await db.get_active_user_ids())
    await message.reply(texts.BROADCAST_CONFIRM.format(count=count), reply_markup=kb.broadcast_confirm())


async def broadcast_use_buttons(message: Message) -> None:
    await message.answer(texts.USE_BUTTONS)


async def broadcast_send(callback: CallbackQuery, state: FSMContext, bot: Bot, db: Database) -> None:
    await ack(callback)
    data = await state.get_data()
    await state.clear()
    if "from_chat_id" not in data or "message_id" not in data:
        await safe_edit(callback, bot, texts.BROADCAST_CANCELLED)
        return

    count = len(await db.get_active_user_ids())
    await safe_edit(callback, bot, texts.BROADCAST_STARTED.format(count=count))
    # Рассылка идёт в фоне: хендлер сразу освобождается, админ может пользоваться ботом дальше.
    tasks.spawn(
        _broadcast_and_report(bot, db, callback_chat_id(callback), data["from_chat_id"], data["message_id"]),
        name="broadcast",
    )


async def _broadcast_and_report(
    bot: Bot, db: Database, report_chat_id: int, from_chat_id: int, message_id: int
) -> None:
    try:
        result = await run_broadcast(bot, db, from_chat_id, message_id)
    except Exception:
        logger.exception("Рассылка прервана из-за ошибки")
        await bot.send_message(report_chat_id, texts.BROADCAST_FAILED)
        return
    await bot.send_message(
        report_chat_id,
        texts.BROADCAST_DONE.format(sent=result.sent, blocked=result.blocked, failed=result.failed),
    )


async def broadcast_cancel(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await ack(callback)
    await state.clear()
    await safe_edit(callback, bot, texts.BROADCAST_CANCELLED)


# -- статусы заявок -------------------------------------------------------------------


async def lead_status_changed(
    callback: CallbackQuery, callback_data: LeadStatusCb, db: Database, config: Config, bot: Bot
) -> None:
    if not config.is_admin(callback.from_user.id):
        await ack(callback, texts.NOT_ADMIN, show_alert=True)
        return
    if callback_data.status not in LEAD_STATUSES:
        await ack(callback, texts.STALE_BUTTON, show_alert=True)
        return
    lead = await db.set_lead_status(callback_data.lead_id, callback_data.status)
    if lead is None:
        await ack(callback, texts.LEAD_NOT_FOUND, show_alert=True)
        await drop_keyboard(callback)
        return
    await ack(callback, texts.ADMIN_STATUS_CHANGED.format(status=status_title(lead.status)))
    await safe_edit(callback, bot, render_lead_card(lead, config.tz), kb.lead_status(lead.id, lead.status))
    logger.info("Админ %s: заявка #%s -> %s", callback.from_user.id, lead.id, lead.status)


def create_router() -> Router:
    router = Router(name="admin")
    router.message.filter(IsAdmin())

    router.message.register(cmd_leads, Command("leads"))
    router.message.register(cmd_export, Command("export"))
    router.message.register(cmd_stats, Command("stats"))
    router.message.register(cmd_broadcast, Command("broadcast"))
    router.message.register(broadcast_message_received, BroadcastForm.waiting_message)
    router.message.register(broadcast_use_buttons, BroadcastForm.confirm)

    router.callback_query.register(
        broadcast_send, BroadcastForm.confirm, BroadcastCb.filter(F.action == "send"), IsAdmin()
    )
    router.callback_query.register(
        broadcast_cancel, BroadcastForm.confirm, BroadcastCb.filter(F.action == "cancel"), IsAdmin()
    )
    # Без IsAdmin на уровне фильтра: не-админ в общем чате получит понятный ответ «Недостаточно прав».
    router.callback_query.register(lead_status_changed, LeadStatusCb.filter())
    return router
