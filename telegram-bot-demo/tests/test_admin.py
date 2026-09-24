"""Сквозные тесты админ-функций: /leads, /export, /stats, рассылка, статусы, меню команд."""

import csv
import io
import logging

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery, CopyMessage, EditMessageText, SendDocument, SetMyCommands
from aiogram.types import BotCommandScopeAllPrivateChats, BotCommandScopeChat, BufferedInputFile

from bot import texts
from bot.app import on_startup
from bot.callbacks import BroadcastCb, LeadStatusCb
from bot.db import Database
from bot.services import tasks
from tests.conftest import ADMIN_GROUP_ID, ADMIN_ID, CLIENT_ID
from tests.fakes import FakeSession, TgClient


async def seed_leads(db: Database, count: int) -> None:
    for i in range(count):
        await db.add_lead(
            user_id=1000 + i,
            username=f"user{i}",
            tg_full_name=f"User {i}",
            name=f"Клиент {i}" if i else "=ФОРМУЛА",
            phone="+7900123456" + str(i % 10),
            service="landing" if i % 2 else "shop",
            comment=f"комментарий {i}",
        )


# -- доступ -------------------------------------------------------------------------------------


@pytest.mark.parametrize("command", ["/leads", "/export", "/stats", "/broadcast"])
async def test_admin_commands_hidden_from_regular_users(
    client: TgClient, session: FakeSession, db: Database, command: str
) -> None:
    await seed_leads(db, 2)
    await client.send(command)
    assert session.last_text_to(CLIENT_ID) == texts.UNKNOWN
    assert not session.of_type(SendDocument)


async def test_admin_help_lists_admin_commands(admin: TgClient, session: FakeSession) -> None:
    await admin.send("/help")
    assert "/broadcast" in session.last_text_to(ADMIN_ID)


# -- /leads /export /stats ------------------------------------------------------------------


async def test_leads_empty_and_last_ten(admin: TgClient, session: FakeSession, db: Database) -> None:
    await admin.send("/leads")
    assert session.last_text_to(ADMIN_ID) == texts.LEADS_EMPTY

    await seed_leads(db, 12)
    await admin.send("/leads")
    text = session.last_text_to(ADMIN_ID)
    assert "Последние заявки</b> (10)" in text
    assert "№12" in text and "№3" in text
    assert "№2" not in text


async def test_export_csv(admin: TgClient, session: FakeSession, db: Database) -> None:
    await admin.send("/export")
    assert session.last_text_to(ADMIN_ID) == texts.LEADS_EMPTY

    await seed_leads(db, 3)
    await admin.send("/export")
    [request] = session.of_type(SendDocument)
    assert request.chat_id == ADMIN_ID
    assert "3 шт." in request.caption
    document = request.document
    assert isinstance(document, BufferedInputFile)
    assert document.filename.startswith("leads_") and document.filename.endswith(".csv")

    rows = list(csv.reader(io.StringIO(document.data.decode("utf-8-sig")), delimiter=";"))
    assert len(rows) == 4
    assert rows[1][3] == "'=ФОРМУЛА"  # защита от CSV-инъекций


async def test_stats(admin: TgClient, client: TgClient, session: FakeSession, db: Database) -> None:
    await client.send("/start")
    await seed_leads(db, 3)
    await admin.send("/stats")
    text = session.last_text_to(ADMIN_ID)
    assert "Статистика" in text
    assert "Заявок всего: <b>3</b>" in text
    assert "• Интернет-магазин: 2" in text


async def test_admin_commands_work_in_admin_group(admin_in_group: TgClient, session: FakeSession, db: Database) -> None:
    await seed_leads(db, 1)
    await admin_in_group.send("/leads")
    assert "№1" in session.last_text_to(ADMIN_GROUP_ID)

    session.clear()
    await admin_in_group.send("обычное сообщение в группе")
    await admin_in_group.send("отмена")
    assert session.messages_to(ADMIN_GROUP_ID) == [], "в группе бот не должен отвечать на всё подряд"


# -- статусы заявок -------------------------------------------------------------------------------


async def test_admin_changes_lead_status(admin: TgClient, session: FakeSession, db: Database) -> None:
    await seed_leads(db, 1)
    await admin.click(LeadStatusCb(lead_id=1, status="in_progress").pack())

    lead = await db.get_lead(1)
    assert lead is not None and lead.status == "in_progress"
    edit = session.of_type(EditMessageText)[-1]
    assert "Статус: 🟡 В работе" in edit.text
    statuses_on_buttons = [b.text for row in edit.reply_markup.inline_keyboard for b in row]
    assert texts.LEAD_STATUSES["in_progress"] not in statuses_on_buttons
    assert texts.LEAD_STATUSES["done"] in statuses_on_buttons


async def test_non_admin_cannot_change_status(client: TgClient, session: FakeSession, db: Database) -> None:
    await seed_leads(db, 1)
    await client.click(LeadStatusCb(lead_id=1, status="done").pack())
    answer = session.of_type(AnswerCallbackQuery)[-1]
    assert answer.text == texts.NOT_ADMIN and answer.show_alert
    assert (await db.get_lead(1)).status == "new"


async def test_status_for_missing_lead(admin: TgClient, session: FakeSession) -> None:
    await admin.click(LeadStatusCb(lead_id=404, status="done").pack())
    assert session.of_type(AnswerCallbackQuery)[-1].text == texts.LEAD_NOT_FOUND


# -- рассылка ------------------------------------------------------------------------------------


async def test_broadcast_with_confirmation(admin: TgClient, session: FakeSession, db: Database) -> None:
    for uid in (1, 2, 3):
        await db.upsert_user(uid, None, f"U{uid}")
    session.blocked_chats.add(2)  # пользователь 2 заблокировал бота

    await admin.send("/broadcast")
    assert "Получателей: <b>3</b>" in session.last_text_to(ADMIN_ID)

    source = await admin.send("🔥 Скидка 20% на лендинги до конца месяца!")
    confirm = session.messages_to(ADMIN_ID)[-1]
    assert "Разослать это сообщение <b>3</b>" in confirm.text
    assert confirm.reply_parameters.message_id == source.message_id
    assert not session.of_type(CopyMessage), "до подтверждения ничего не отправляется"

    await admin.send("ещё текст")  # на шаге подтверждения ждём кнопку
    assert session.last_text_to(ADMIN_ID) == texts.USE_BUTTONS

    await admin.click(BroadcastCb(action="send").pack())
    assert texts.BROADCAST_STARTED.format(count=3) == session.of_type(EditMessageText)[-1].text
    await tasks.wait_all()  # рассылка идёт в фоне
    copies = session.of_type(CopyMessage)
    assert sorted(c.chat_id for c in copies) == [1, 2, 3]
    assert all(c.from_chat_id == ADMIN_ID and c.message_id == source.message_id for c in copies)

    report = session.last_text_to(ADMIN_ID)
    assert "Доставлено: 2" in report and "Заблокировали бота: 1" in report and "Ошибки: 0" in report
    assert await db.get_active_user_ids() == [1, 3]


async def test_broadcast_cancel(admin: TgClient, session: FakeSession, db: Database) -> None:
    await db.upsert_user(1, None, "U1")
    await admin.send("/broadcast")
    await admin.send("текст")
    await admin.click(BroadcastCb(action="cancel").pack())
    assert not session.of_type(CopyMessage)
    assert session.of_type(EditMessageText)[-1].text == texts.BROADCAST_CANCELLED


async def test_broadcast_cancel_command_while_waiting(admin: TgClient, session: FakeSession, db: Database) -> None:
    await db.upsert_user(1, None, "U1")
    await admin.send("/broadcast")
    await admin.send("/cancel")  # не должно уйти в рассылку как контент
    assert session.last_text_to(ADMIN_ID) == texts.BROADCAST_CANCELLED
    await admin.click(BroadcastCb(action="send").pack())
    await tasks.wait_all()
    assert not session.of_type(CopyMessage)


async def test_broadcast_without_recipients(admin: TgClient, session: FakeSession) -> None:
    await admin.send("/broadcast")
    assert session.last_text_to(ADMIN_ID) == texts.BROADCAST_NO_RECIPIENTS


# -- запуск -----------------------------------------------------------------------------------------


async def test_startup_sets_commands_and_survives_unknown_admin(
    bot, config, session: FakeSession, caplog: pytest.LogCaptureFixture
) -> None:
    def fail_for_admin_scope(method: SetMyCommands) -> Exception | None:
        if isinstance(method.scope, BotCommandScopeChat):
            return TelegramBadRequest(method=method, message="Bad Request: chat not found")
        return None

    session.raise_for[SetMyCommands] = fail_for_admin_scope
    with caplog.at_level(logging.WARNING):
        await on_startup(bot, config)

    calls = session.of_type(SetMyCommands)
    assert isinstance(calls[0].scope, BotCommandScopeAllPrivateChats)
    assert [c.command for c in calls[0].commands] == [cmd for cmd, _ in texts.USER_COMMANDS]
    admin_call = calls[1]
    assert admin_call.scope.chat_id == ADMIN_ID
    assert "leads" in [c.command for c in admin_call.commands]
    assert "Не удалось установить меню команд" in caplog.text


async def test_broadcast_failure_is_reported(
    admin: TgClient, session: FakeSession, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    await db.upsert_user(1, None, "U1")
    await admin.send("/broadcast")
    await admin.send("текст")

    async def broken_get_active_user_ids():
        raise RuntimeError("database is locked")

    monkeypatch.setattr(db, "get_active_user_ids", broken_get_active_user_ids)
    # счётчик получателей в хендлере тоже упадёт — проверяем, что это не роняет бота
    await admin.click(BroadcastCb(action="send").pack())
    await tasks.wait_all()
    assert session.last_text_to(ADMIN_ID) == texts.ERROR_GENERIC


async def test_background_broadcast_error_reported_to_admin(
    bot, db: Database, session: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bot.handlers import admin as admin_handlers

    async def broken_run_broadcast(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(admin_handlers, "run_broadcast", broken_run_broadcast)
    await admin_handlers._broadcast_and_report(bot, db, ADMIN_ID, ADMIN_ID, 1)
    assert session.last_text_to(ADMIN_ID) == texts.BROADCAST_FAILED
