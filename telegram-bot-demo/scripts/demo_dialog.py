"""Показывает диалог с ботом прямо в терминале — без токена и без интернета.

Запускает настоящие хендлеры на фейковом Telegram (tests/fakes.py) и печатает
переписку клиента и администратора.

    python scripts/demo_dialog.py
"""

from __future__ import annotations

import asyncio
import html
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aiogram.methods import AnswerCallbackQuery, CopyMessage, EditMessageText, SendDocument, SendMessage  # noqa: E402
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, User  # noqa: E402

from bot.app import create_bot, create_dispatcher  # noqa: E402
from bot.callbacks import FormCb, MenuCb, ServiceCb  # noqa: E402
from bot.config import Config  # noqa: E402
from bot.db import Database  # noqa: E402
from tests.fakes import FakeSession, TgClient  # noqa: E402

ADMIN_ID = 1
CLIENT_ID = 2
WIDTH = 72


def plain(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or ""))


def keyboard(markup: object) -> str:
    if isinstance(markup, InlineKeyboardMarkup):
        rows = markup.inline_keyboard
    elif isinstance(markup, ReplyKeyboardMarkup):
        rows = markup.keyboard
    else:
        return ""
    return "\n".join("   " + "  ".join(f"[{b.text}]" for b in row) for row in rows)


def print_bot_output(session: FakeSession, start: int, who: dict[int, str]) -> None:
    for request in session.requests[start:]:
        if isinstance(request, SendMessage):
            label = who.get(request.chat_id, str(request.chat_id))
            print(f"🤖 → {label}:")
        elif isinstance(request, EditMessageText):
            print("🤖 (обновил сообщение):")
        elif isinstance(request, SendDocument):
            print(f"🤖 → файл {request.document.filename}: {plain(request.caption)}")
            continue
        elif isinstance(request, CopyMessage):
            print(f"🤖 → копия рассылки пользователю {request.chat_id}")
            continue
        elif isinstance(request, AnswerCallbackQuery) and request.text:
            print(f"🤖 (всплывающее уведомление): {request.text}")
            continue
        else:
            continue
        for line in plain(request.text).splitlines():
            print(f"   {line}")
        kb = keyboard(request.reply_markup)
        if kb:
            print(kb)
    print()


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config = Config(
            bot_token="123456789:AAFakeTokenForDemoDialog_abcdefghijk",
            admin_ids=frozenset({ADMIN_ID}),
            admin_chat_ids=(ADMIN_ID,),
            db_path=Path(tmp) / "demo.db",
            lead_cooldown_minutes=0,
        )
        session = FakeSession()
        bot = create_bot(config, session=session)
        async with Database(config.db_path) as db:
            dp = create_dispatcher(config, db)
            client = TgClient(dp, bot, User(id=CLIENT_ID, is_bot=False, first_name="Анна", username="anna"))
            admin = TgClient(dp, bot, User(id=ADMIN_ID, is_bot=False, first_name="Менеджер"))
            who = {CLIENT_ID: "Анна", ADMIN_ID: "Админ"}

            steps: list[tuple[str, TgClient, str, str]] = [
                ("Анна", client, "send", "/start"),
                ("Анна", client, "click", MenuCb(section="prices").pack()),
                ("Анна", client, "click", MenuCb(section="apply").pack()),
                ("Анна", client, "send", "Анна"),
                ("Анна", client, "send", "8 900 12"),
                ("Анна", client, "send", "8 (900) 123-45-67"),
                ("Анна", client, "click", ServiceCb(code="landing").pack()),
                ("Анна", client, "send", "Лендинг для кофейни, запуск через 2 недели"),
                ("Анна", client, "click", FormCb(action="submit").pack()),
                ("Админ", admin, "send", "/stats"),
                ("Админ", admin, "send", "/export"),
            ]
            labels = {
                MenuCb(section="prices").pack(): "💰 Цены",
                MenuCb(section="apply").pack(): "📝 Оставить заявку",
                ServiceCb(code="landing").pack(): "Лендинг",
                FormCb(action="submit").pack(): "✅ Отправить",
            }

            print("=" * WIDTH)
            print("Демо-диалог с ботом «Ромашка Digital» (демо-проект, компания вымышлена)")
            print("=" * WIDTH + "\n")
            for name, actor, action, payload in steps:
                start = len(session.requests)
                if action == "send":
                    print(f"👤 {name}: {payload}")
                    await actor.send(payload)
                else:
                    print(f"👤 {name} нажимает [{labels.get(payload, payload)}]")
                    await actor.click(payload)
                print_bot_output(session, start, who)


if __name__ == "__main__":
    asyncio.run(main())
