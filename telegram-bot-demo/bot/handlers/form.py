"""Анкета-заявка (FSM): имя → телефон → услуга → комментарий → подтверждение.

С экрана подтверждения можно вернуться к любому полю; после исправления
пользователь сразу попадает обратно на подтверждение, а не проходит анкету заново.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import CallbackQuery, Message, User

from bot import keyboards as kb
from bot import texts
from bot.callbacks import EditCb, FormCb, MenuCb, ServiceCb
from bot.config import Config
from bot.db import Database
from bot.formatting import esc, render_confirm, render_summary, service_title
from bot.handlers.common import cancel_flow
from bot.handlers.utils import ack, callback_chat_id, drop_keyboard, safe_edit
from bot.services.notify import notify_admins
from bot.states import LeadForm
from bot.validators import (
    COMMENT_MAX_LEN,
    comment_is_valid,
    format_phone,
    normalize_comment,
    normalize_name,
    normalize_phone,
)

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ("name", "phone", "service")
FIELD_STATES: dict[str, State] = {
    "name": LeadForm.name,
    "phone": LeadForm.phone,
    "service": LeadForm.service,
    "comment": LeadForm.comment,
}
NEXT_STEP = {"name": "phone", "phone": "service", "service": "comment", "comment": "confirm"}
_FORM_STATES = frozenset(s.state for s in LeadForm.__all_states__)


# -- навигация по шагам ----------------------------------------------------------


async def ask_step(step: str, *, bot: Bot, chat_id: int, state: FSMContext, user: User | None) -> None:
    """Переводит анкету на шаг ``step`` и задаёт соответствующий вопрос."""
    if step == "confirm":
        await state.set_state(LeadForm.confirm)
        data = await state.get_data()
        await bot.send_message(chat_id, render_confirm(data), reply_markup=kb.confirm_step())
        return

    await state.set_state(FIELD_STATES[step])
    if step == "name":
        suggested = normalize_name(user.first_name) if user else None
        await bot.send_message(chat_id, texts.ASK_NAME, reply_markup=kb.name_step(suggested))
    elif step == "phone":
        await bot.send_message(
            chat_id,
            texts.ASK_PHONE.format(button=esc(texts.BTN_SHARE_PHONE)),
            reply_markup=kb.phone_step(),
        )
    elif step == "service":
        await bot.send_message(chat_id, texts.ASK_SERVICE, reply_markup=kb.services_step())
    elif step == "comment":
        await bot.send_message(chat_id, texts.ASK_COMMENT, reply_markup=kb.comment_step())


async def after_field(field: str, *, bot: Bot, chat_id: int, state: FSMContext, user: User | None) -> None:
    """Следующий шаг после заполнения поля: по порядку или сразу к подтверждению (режим правки)."""
    data = await state.get_data()
    step = "confirm" if data.get("editing") else NEXT_STEP[field]
    await ask_step(step, bot=bot, chat_id=chat_id, state=state, user=user)


async def start_form(*, bot: Bot, chat_id: int, user: User, state: FSMContext, db: Database, config: Config) -> None:
    if config.lead_cooldown_minutes > 0:
        last = await db.last_lead_time(user.id)
        if last is not None:
            cooldown = timedelta(minutes=config.lead_cooldown_minutes)
            elapsed = datetime.now(UTC) - last
            if elapsed < cooldown:
                left = max(1, math.ceil((cooldown - elapsed).total_seconds() / 60))
                await bot.send_message(chat_id, texts.COOLDOWN.format(left=left), reply_markup=kb.back_to_menu())
                return

    previous = await state.get_state()
    await state.clear()
    if previous in _FORM_STATES:
        # Анкету начали заново посреди старой: убираем оставшуюся клавиатуру «Отправить мой номер».
        await bot.send_message(chat_id, texts.FORM_RESTARTED, reply_markup=kb.remove_reply())
    await ask_step("name", bot=bot, chat_id=chat_id, state=state, user=user)


# -- точки входа -------------------------------------------------------------------


async def cmd_apply(message: Message, state: FSMContext, db: Database, config: Config, bot: Bot) -> None:
    if message.from_user is None:
        return
    await start_form(bot=bot, chat_id=message.chat.id, user=message.from_user, state=state, db=db, config=config)


async def cb_apply(callback: CallbackQuery, state: FSMContext, db: Database, config: Config, bot: Bot) -> None:
    await ack(callback)
    await start_form(
        bot=bot, chat_id=callback_chat_id(callback), user=callback.from_user, state=state, db=db, config=config
    )


# -- шаг 1: имя ----------------------------------------------------------------------


async def name_entered(message: Message, state: FSMContext, bot: Bot) -> None:
    name = normalize_name(message.text)
    if name is None:
        await message.answer(texts.NAME_INVALID)
        return
    await state.update_data(name=name)
    await after_field("name", bot=bot, chat_id=message.chat.id, state=state, user=message.from_user)


async def name_from_profile(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    name = normalize_name(callback.from_user.first_name)
    if name is None:
        await ack(callback, texts.NAME_NOT_TEXT, show_alert=True)
        return
    await ack(callback)
    await state.update_data(name=name)
    await safe_edit(callback, bot, texts.NAME_CHOSEN.format(name=esc(name)))
    await after_field("name", bot=bot, chat_id=callback_chat_id(callback), state=state, user=callback.from_user)


async def name_not_text(message: Message) -> None:
    await message.answer(texts.NAME_NOT_TEXT)


# -- шаг 2: телефон ------------------------------------------------------------------


async def _save_phone(message: Message, state: FSMContext, bot: Bot, raw: str | None) -> None:
    phone = normalize_phone(raw)
    if phone is None:
        await message.answer(
            texts.PHONE_INVALID.format(button=esc(texts.BTN_SHARE_PHONE)),
            reply_markup=kb.phone_step(),
        )
        return
    await state.update_data(phone=phone)
    # Отдельное сообщение нужно, чтобы убрать reply-клавиатуру «Отправить мой номер».
    await message.answer(texts.PHONE_SAVED.format(phone=esc(format_phone(phone))), reply_markup=kb.remove_reply())
    await after_field("phone", bot=bot, chat_id=message.chat.id, state=state, user=message.from_user)


async def phone_from_contact(message: Message, state: FSMContext, bot: Bot) -> None:
    contact = message.contact
    assert contact is not None
    sender_id = message.from_user.id if message.from_user else None
    if contact.user_id is not None and contact.user_id != sender_id:
        await message.answer(texts.CONTACT_NOT_OWN.format(button=esc(texts.BTN_SHARE_PHONE)))
        return
    await _save_phone(message, state, bot, contact.phone_number)


async def phone_from_text(message: Message, state: FSMContext, bot: Bot) -> None:
    await _save_phone(message, state, bot, message.text)


async def phone_invalid_content(message: Message) -> None:
    await message.answer(texts.PHONE_INVALID.format(button=esc(texts.BTN_SHARE_PHONE)), reply_markup=kb.phone_step())


# -- шаг 3: услуга -------------------------------------------------------------------


async def service_chosen(callback: CallbackQuery, callback_data: ServiceCb, state: FSMContext, bot: Bot) -> None:
    if callback_data.code not in texts.SERVICES:
        await ack(callback, texts.STALE_BUTTON, show_alert=True)
        return
    await ack(callback)
    await state.update_data(service=callback_data.code)
    await safe_edit(callback, bot, texts.SERVICE_CHOSEN.format(service=esc(service_title(callback_data.code))))
    await after_field("service", bot=bot, chat_id=callback_chat_id(callback), state=state, user=callback.from_user)


async def service_use_buttons(message: Message) -> None:
    await message.answer(texts.ASK_SERVICE, reply_markup=kb.services_step())


# -- шаг 4: комментарий --------------------------------------------------------------


async def comment_entered(message: Message, state: FSMContext, bot: Bot) -> None:
    comment = normalize_comment(message.text)
    if not comment_is_valid(comment):
        await message.answer(texts.COMMENT_INVALID.format(limit=COMMENT_MAX_LEN, length=len(comment)))
        return
    await state.update_data(comment=comment)
    await after_field("comment", bot=bot, chat_id=message.chat.id, state=state, user=message.from_user)


async def comment_skipped(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await ack(callback)
    await state.update_data(comment="")
    await safe_edit(callback, bot, texts.COMMENT_SKIPPED)
    await after_field("comment", bot=bot, chat_id=callback_chat_id(callback), state=state, user=callback.from_user)


async def comment_not_text(message: Message) -> None:
    await message.answer(texts.COMMENT_NOT_TEXT, reply_markup=kb.comment_step())


# -- подтверждение и правка ----------------------------------------------------------


async def confirm_edit_menu(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await ack(callback)
    data = await state.get_data()
    await safe_edit(callback, bot, f"{render_summary(data)}\n\n{texts.ASK_EDIT_FIELD}", kb.edit_fields())


async def confirm_back(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await ack(callback)
    data = await state.get_data()
    await safe_edit(callback, bot, render_confirm(data), kb.confirm_step())


async def confirm_edit_field(callback: CallbackQuery, callback_data: EditCb, state: FSMContext, bot: Bot) -> None:
    if callback_data.field not in FIELD_STATES:
        await ack(callback, texts.STALE_BUTTON, show_alert=True)
        return
    await ack(callback)
    await state.update_data(editing=True)
    data = await state.get_data()
    await safe_edit(callback, bot, render_summary(data))  # «замораживаем» старую карточку без кнопок
    await ask_step(
        callback_data.field, bot=bot, chat_id=callback_chat_id(callback), state=state, user=callback.from_user
    )


async def confirm_submit(callback: CallbackQuery, state: FSMContext, bot: Bot, db: Database, config: Config) -> None:
    await ack(callback)
    chat_id = callback_chat_id(callback)
    data = await state.get_data()

    if any(not data.get(key) for key in REQUIRED_FIELDS):
        await state.clear()
        await bot.send_message(chat_id, texts.FORM_EXPIRED, reply_markup=kb.main_menu())
        return

    # Снимаем состояние сразу, чтобы повторное нажатие «Отправить» не создало дубль.
    await state.set_state(None)
    user = callback.from_user
    try:
        await db.upsert_user(user.id, user.username, user.full_name)
        lead = await db.add_lead(
            user_id=user.id,
            username=user.username,
            tg_full_name=user.full_name,
            name=data["name"],
            phone=data["phone"],
            service=data["service"],
            comment=data.get("comment", ""),
        )
    except Exception:
        await state.set_state(LeadForm.confirm)  # данные не потеряны, можно нажать ещё раз
        raise

    await state.clear()
    logger.info("Новая заявка #%s от пользователя %s (услуга: %s)", lead.id, user.id, lead.service)

    # Заявка уже в БД: сбой при ответе клиенту не должен помешать уведомить менеджеров.
    try:
        await safe_edit(callback, bot, render_summary(data))
        await bot.send_message(
            chat_id,
            texts.LEAD_SENT.format(name=esc(lead.name), lead_id=lead.id),
            reply_markup=kb.main_menu(),
        )
    except TelegramAPIError:
        logger.warning("Заявка #%s сохранена, но подтверждение клиенту не отправлено", lead.id, exc_info=True)
    await notify_admins(bot, config.admin_chat_ids, lead, config.tz)


async def confirm_use_buttons(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await message.answer(render_confirm(data), reply_markup=kb.confirm_step())


async def form_cancel(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await ack(callback)
    await drop_keyboard(callback)
    await cancel_flow(bot, callback_chat_id(callback), state)


def create_router() -> Router:
    router = Router(name="form")
    router.message.filter(F.chat.type == ChatType.PRIVATE)
    router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)

    # вход
    router.message.register(cmd_apply, Command("apply"))
    router.callback_query.register(cb_apply, MenuCb.filter(F.section == "apply"))
    router.callback_query.register(form_cancel, FormCb.filter(F.action == "cancel"))

    # имя
    router.message.register(name_entered, LeadForm.name, F.text)
    router.callback_query.register(name_from_profile, LeadForm.name, FormCb.filter(F.action == "use_tg_name"))
    router.message.register(name_not_text, LeadForm.name)

    # телефон
    router.message.register(phone_from_contact, LeadForm.phone, F.contact)
    router.message.register(phone_from_text, LeadForm.phone, F.text)
    router.message.register(phone_invalid_content, LeadForm.phone)

    # услуга
    router.callback_query.register(service_chosen, LeadForm.service, ServiceCb.filter())
    router.message.register(service_use_buttons, LeadForm.service)

    # комментарий
    router.message.register(comment_entered, LeadForm.comment, F.text)
    router.callback_query.register(comment_skipped, LeadForm.comment, FormCb.filter(F.action == "skip_comment"))
    router.message.register(comment_not_text, LeadForm.comment)

    # подтверждение
    router.callback_query.register(confirm_submit, LeadForm.confirm, FormCb.filter(F.action == "submit"))
    router.callback_query.register(confirm_edit_menu, LeadForm.confirm, FormCb.filter(F.action == "edit"))
    router.callback_query.register(confirm_back, LeadForm.confirm, FormCb.filter(F.action == "back"))
    router.callback_query.register(confirm_edit_field, LeadForm.confirm, EditCb.filter())
    router.message.register(confirm_use_buttons, LeadForm.confirm)
    return router
