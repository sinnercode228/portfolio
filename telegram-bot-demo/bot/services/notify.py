"""Мгновенные уведомления администраторов о новых заявках."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from datetime import tzinfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter

from bot import keyboards
from bot.db import Lead
from bot.formatting import render_lead_card

logger = logging.getLogger(__name__)


async def notify_admins(bot: Bot, chat_ids: Iterable[int], lead: Lead, tz: tzinfo) -> int:
    """Отправляет карточку заявки во все админ-чаты.

    Ошибка в одном чате не мешает остальным. Возвращает число успешных доставок.
    Заявка к этому моменту уже сохранена в БД, поэтому даже при полном сбое
    уведомлений она не теряется и видна в /leads и /export.
    """
    chat_ids = list(chat_ids)
    if not chat_ids:
        logger.warning("Заявка #%s сохранена, но ADMIN_CHAT_IDS/ADMIN_IDS не заданы", lead.id)
        return 0

    text = render_lead_card(lead, tz)
    markup = keyboards.lead_status(lead.id, lead.status)
    delivered = 0
    for chat_id in chat_ids:
        for attempt in (1, 2):
            try:
                await bot.send_message(chat_id, text, reply_markup=markup)
                delivered += 1
                break
            except TelegramRetryAfter as exc:
                if attempt == 2:
                    logger.error("Чат %s: флуд-лимит, заявка #%s не доставлена", chat_id, lead.id)
                    break
                logger.warning("Флуд-лимит Telegram, ждём %s с", exc.retry_after)
                await asyncio.sleep(exc.retry_after)
            except TelegramAPIError as exc:
                logger.error("Не удалось уведомить чат %s о заявке #%s: %s", chat_id, lead.id, exc)
                break

    if not delivered:
        logger.error("Заявка #%s не доставлена ни в один админ-чат (сохранена в БД)", lead.id)
    return delivered
