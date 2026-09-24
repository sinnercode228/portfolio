"""Клавиатуры бота."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import texts
from bot.callbacks import BroadcastCb, EditCb, FormCb, LeadStatusCb, MenuCb, ServiceCb


def main_menu() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_SERVICES, callback_data=MenuCb(section="services"))
    b.button(text=texts.BTN_PRICES, callback_data=MenuCb(section="prices"))
    b.button(text=texts.BTN_APPLY, callback_data=MenuCb(section="apply"))
    b.button(text=texts.BTN_FAQ, callback_data=MenuCb(section="faq"))
    b.button(text=texts.BTN_CONTACTS, callback_data=MenuCb(section="contacts"))
    b.adjust(2, 1, 2)
    return b.as_markup()


def section_nav() -> InlineKeyboardMarkup:
    """Кнопки под разделом меню: призыв оставить заявку + возврат."""
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_APPLY, callback_data=MenuCb(section="apply"))
    b.button(text=texts.BTN_BACK, callback_data=MenuCb(section="home"))
    b.adjust(1)
    return b.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_BACK, callback_data=MenuCb(section="home"))
    return b.as_markup()


def name_step(suggested_name: str | None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if suggested_name:
        b.button(
            text=texts.BTN_USE_NAME.format(name=suggested_name),
            callback_data=FormCb(action="use_tg_name"),
        )
    b.button(text=texts.BTN_CANCEL, callback_data=FormCb(action="cancel"))
    b.adjust(1)
    return b.as_markup()


def phone_step() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_SHARE_PHONE, request_contact=True)],
            [KeyboardButton(text=texts.BTN_CANCEL)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="+7 900 123-45-67",
    )


def remove_reply() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def services_step() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for code, service in texts.SERVICES.items():
        b.button(text=service.title, callback_data=ServiceCb(code=code))
    b.adjust(2)
    # «Отмена» — отдельной строкой, чтобы её не путали с вариантом услуги
    b.row(InlineKeyboardButton(text=texts.BTN_CANCEL, callback_data=FormCb(action="cancel").pack()))
    return b.as_markup()


def comment_step() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_SKIP, callback_data=FormCb(action="skip_comment"))
    b.button(text=texts.BTN_CANCEL, callback_data=FormCb(action="cancel"))
    b.adjust(2)
    return b.as_markup()


def confirm_step() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_SUBMIT, callback_data=FormCb(action="submit"))
    b.button(text=texts.BTN_EDIT, callback_data=FormCb(action="edit"))
    b.button(text=texts.BTN_CANCEL, callback_data=FormCb(action="cancel"))
    b.adjust(1, 2)
    return b.as_markup()


def edit_fields() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_EDIT_NAME, callback_data=EditCb(field="name"))
    b.button(text=texts.BTN_EDIT_PHONE, callback_data=EditCb(field="phone"))
    b.button(text=texts.BTN_EDIT_SERVICE, callback_data=EditCb(field="service"))
    b.button(text=texts.BTN_EDIT_COMMENT, callback_data=EditCb(field="comment"))
    b.button(text=texts.BTN_BACK_TO_CONFIRM, callback_data=FormCb(action="back"))
    b.adjust(2, 2, 1)
    return b.as_markup()


def lead_status(lead_id: int, current: str) -> InlineKeyboardMarkup:
    """Кнопки смены статуса под карточкой заявки у администратора."""
    b = InlineKeyboardBuilder()
    for status, title in texts.LEAD_STATUSES.items():
        if status != current:
            b.button(text=title, callback_data=LeadStatusCb(lead_id=lead_id, status=status))
    b.adjust(3)
    return b.as_markup()


def broadcast_confirm() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_BROADCAST_SEND, callback_data=BroadcastCb(action="send"))
    b.button(text=texts.BTN_BROADCAST_CANCEL, callback_data=BroadcastCb(action="cancel"))
    b.adjust(2)
    return b.as_markup()
