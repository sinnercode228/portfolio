"""Навигация по inline-меню: Услуги, Цены, FAQ, Контакты."""

from __future__ import annotations

from collections.abc import Callable

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from bot import keyboards as kb
from bot.callbacks import MenuCb
from bot.formatting import render_contacts, render_faq, render_menu, render_prices, render_services
from bot.handlers.utils import ack, safe_edit

SECTIONS: dict[str, Callable[[], str]] = {
    "services": render_services,
    "prices": render_prices,
    "faq": render_faq,
    "contacts": render_contacts,
}


async def show_home(callback: CallbackQuery, bot: Bot) -> None:
    await ack(callback)
    await safe_edit(callback, bot, render_menu(), kb.main_menu())


async def show_section(callback: CallbackQuery, callback_data: MenuCb, bot: Bot) -> None:
    await ack(callback)
    await safe_edit(callback, bot, SECTIONS[callback_data.section](), kb.section_nav())


def create_router() -> Router:
    router = Router(name="menu")
    router.callback_query.register(show_home, MenuCb.filter(F.section == "home"))
    router.callback_query.register(show_section, MenuCb.filter(F.section.in_(SECTIONS.keys())))
    return router
