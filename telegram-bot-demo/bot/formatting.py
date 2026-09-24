"""Сборка сообщений из шаблонов texts.py.

Любые данные от пользователя проходят через :func:`esc`, поэтому ввод вида
``<b>`` или ``&`` не ломает HTML-разметку Telegram и не позволяет внедрить ссылки.
"""

from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from datetime import datetime, tzinfo
from typing import Any

from bot import texts
from bot.db import Lead, Stats
from bot.validators import format_phone

TELEGRAM_MESSAGE_LIMIT = 4096
LIST_COMMENT_PREVIEW = 80


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def truncate(value: str, limit: int) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def format_dt(dt: datetime, tz: tzinfo) -> str:
    return dt.astimezone(tz).strftime("%d.%m.%Y %H:%M")


def service_title(code: str) -> str:
    service = texts.SERVICES.get(code)
    return service.title if service else code


def status_title(status: str) -> str:
    return texts.LEAD_STATUSES.get(status, status)


# -- пользовательские экраны ---------------------------------------------------


def render_start(first_name: str | None) -> str:
    return texts.START.format(
        name=esc(first_name or "друг"),
        brand=esc(texts.BRAND),
        demo_note=texts.DEMO_NOTE,
    )


def render_menu() -> str:
    return texts.MENU.format(brand=esc(texts.BRAND))


def render_services() -> str:
    items = [f"<b>{esc(s.title)}</b>\n{esc(s.description)}" for s in texts.SERVICES.values()]
    return "\n\n".join([texts.SERVICES_HEADER, *items])


def render_prices() -> str:
    items = [
        f"• <b>{esc(s.title)}</b> — {esc(s.price)}"
        + (f" · {esc(s.duration)}" if s.duration and s.duration != "—" else "")
        for s in texts.SERVICES.values()
    ]
    return "\n".join([texts.PRICES_HEADER, "", *items, "", texts.PRICES_FOOTER])


def render_faq() -> str:
    items = [f"<b>{esc(q)}</b>\n{esc(a)}" for q, a in texts.FAQ]
    return "\n\n".join([texts.FAQ_HEADER, *items])


def render_contacts() -> str:
    return f"{texts.CONTACTS}\n\n{texts.DEMO_NOTE}"


def render_help(is_admin: bool) -> str:
    return texts.HELP + (texts.HELP_ADMIN if is_admin else "")


def render_summary(data: Mapping[str, Any]) -> str:
    """Черновик заявки из данных FSM (для экрана подтверждения)."""
    comment = data.get("comment") or ""
    return "\n".join(
        [
            texts.SUMMARY_NAME.format(value=esc(data.get("name", ""))),
            texts.SUMMARY_PHONE.format(value=esc(format_phone(data.get("phone", "")))),
            texts.SUMMARY_SERVICE.format(value=esc(service_title(data.get("service", "")))),
            texts.SUMMARY_COMMENT.format(value=esc(comment) if comment else texts.NO_COMMENT),
        ]
    )


def render_confirm(data: Mapping[str, Any]) -> str:
    return texts.ASK_CONFIRM.format(summary=render_summary(data))


# -- администратор -------------------------------------------------------------


def render_tg_link(lead: Lead) -> str:
    label = esc(lead.tg_full_name or lead.name)
    mention = f'<a href="tg://user?id={int(lead.user_id)}">{label}</a>'
    if lead.username:
        return f"{mention} (@{esc(lead.username)})"
    return f"{mention} (id <code>{int(lead.user_id)}</code>)"


def render_lead_card(lead: Lead, tz: tzinfo) -> str:
    """Карточка заявки для уведомления администратора."""
    return texts.ADMIN_LEAD_CARD.format(
        lead_id=lead.id,
        created=format_dt(lead.created_at, tz),
        name=esc(lead.name),
        phone=esc(format_phone(lead.phone)),
        service=esc(service_title(lead.service)),
        comment=esc(lead.comment) if lead.comment else texts.NO_COMMENT,
        tg_link=render_tg_link(lead),
        status=status_title(lead.status),
    )


def render_leads_list(leads: Sequence[Lead], tz: tzinfo) -> str:
    if not leads:
        return texts.LEADS_EMPTY
    blocks = [texts.LEADS_HEADER.format(count=len(leads))]
    for lead in leads:
        comment = f"\n<i>{esc(truncate(lead.comment, LIST_COMMENT_PREVIEW))}</i>" if lead.comment else ""
        blocks.append(
            texts.LEADS_ITEM.format(
                lead_id=lead.id,
                created=format_dt(lead.created_at, tz),
                status=status_title(lead.status),
                name=esc(lead.name),
                phone=esc(format_phone(lead.phone)),
                service=esc(service_title(lead.service)),
                comment=comment,
            )
        )
    return "\n\n".join(blocks)


def _render_counter(counter: Mapping[str, int], title: Any) -> str:
    if not counter:
        return texts.NO_COMMENT
    return "\n".join(f"• {esc(title(key))}: {value}" for key, value in counter.items())


def render_stats(stats: Stats) -> str:
    return texts.STATS.format(
        users_total=stats.users_total,
        users_blocked=stats.users_blocked,
        leads_total=stats.leads_total,
        unique_clients=stats.unique_clients,
        leads_today=stats.leads_today,
        leads_week=stats.leads_week,
        conversion=f"{stats.conversion:.0%}",
        by_service=_render_counter(stats.by_service, service_title),
        by_status=_render_counter(stats.by_status, status_title),
    )
