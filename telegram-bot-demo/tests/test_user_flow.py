"""Сквозные тесты пользовательских сценариев: настоящие хендлеры aiogram + фейковый Telegram."""

import dataclasses
import logging
from datetime import UTC, datetime

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import (
    ChatMemberBanned,
    ChatMemberMember,
    ChatMemberUpdated,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)

from bot import texts
from bot.app import create_dispatcher
from bot.callbacks import EditCb, FormCb, MenuCb, ServiceCb
from bot.db import Database
from tests.conftest import ADMIN_GROUP_ID, ADMIN_ID, CLIENT_ID
from tests.fakes import BOT_USER, FakeSession, TgClient


def buttons(message: SendMessage | EditMessageText) -> list[str]:
    markup = message.reply_markup
    assert isinstance(markup, InlineKeyboardMarkup)
    return [button.text for row in markup.inline_keyboard for button in row]


async def fill_form_until_confirm(client: TgClient, *, comment: str | None = "Нужен лендинг для кофейни") -> None:
    await client.click(MenuCb(section="apply").pack())
    await client.send("Анна")
    await client.send("+7 900 123-45-67")
    await client.click(ServiceCb(code="landing").pack())
    if comment is None:
        await client.click(FormCb(action="skip_comment").pack())
    else:
        await client.send(comment)


# -- /start и меню -------------------------------------------------------------------------


async def test_start_shows_menu_and_registers_user(client: TgClient, session: FakeSession, db: Database) -> None:
    await client.send("/start")
    message = session.messages_to(CLIENT_ID)[-1]
    assert "Здравствуйте, Анна" in message.text
    assert "Демо-проект" in message.text
    assert buttons(message) == [
        texts.BTN_SERVICES,
        texts.BTN_PRICES,
        texts.BTN_APPLY,
        texts.BTN_FAQ,
        texts.BTN_CONTACTS,
    ]
    assert await db.get_active_user_ids() == [CLIENT_ID]


@pytest.mark.parametrize(
    ("section", "marker"),
    [("services", "Наши услуги"), ("prices", "Цены и сроки"), ("faq", "Частые вопросы"), ("contacts", "Контакты")],
)
async def test_menu_sections(client: TgClient, session: FakeSession, section: str, marker: str) -> None:
    await client.click(MenuCb(section=section).pack())
    edit = session.of_type(EditMessageText)[-1]
    assert marker in edit.text
    assert buttons(edit) == [texts.BTN_APPLY, texts.BTN_BACK]
    assert session.of_type(AnswerCallbackQuery), "каждое нажатие должно получать answerCallbackQuery"

    await client.click(MenuCb(section="home").pack())
    assert "Главное меню" in session.of_type(EditMessageText)[-1].text


async def test_help_and_id(client: TgClient, session: FakeSession) -> None:
    await client.send("/help")
    assert "/apply" in session.last_text_to(CLIENT_ID)
    assert "/leads" not in session.last_text_to(CLIENT_ID)

    await client.send("/id")
    assert f"<code>{CLIENT_ID}</code>" in session.last_text_to(CLIENT_ID)


async def test_unknown_text_returns_menu(client: TgClient, session: FakeSession) -> None:
    await client.send("привет, что умеешь?")
    message = session.messages_to(CLIENT_ID)[-1]
    assert message.text == texts.UNKNOWN
    assert texts.BTN_APPLY in buttons(message)


# -- анкета --------------------------------------------------------------------------------


async def test_full_application_flow(client: TgClient, session: FakeSession, db: Database) -> None:
    await client.send("/start")
    await client.click(MenuCb(section="apply").pack())
    ask_name = session.messages_to(CLIENT_ID)[-1]
    assert "шаг 1 из 4" in ask_name.text
    assert buttons(ask_name) == ["Меня зовут Анна", texts.BTN_CANCEL]

    await client.send("12345")
    assert "Имя должно" in session.last_text_to(CLIENT_ID)

    await client.send("  Анна   Смирнова ")
    ask_phone = session.messages_to(CLIENT_ID)[-1]
    assert "шаг 2 из 4" in ask_phone.text
    assert isinstance(ask_phone.reply_markup, ReplyKeyboardMarkup)
    assert ask_phone.reply_markup.keyboard[0][0].request_contact is True

    await client.send("позвоните мне")
    assert "Не получилось распознать номер" in session.last_text_to(CLIENT_ID)

    await client.send("8 (900) 123-45-67")
    saved, ask_service = session.messages_to(CLIENT_ID)[-2:]
    assert saved.text == "📱 Номер сохранён: +7 (900) 123-45-67"
    assert isinstance(saved.reply_markup, ReplyKeyboardRemove)
    assert "шаг 3 из 4" in ask_service.text
    assert "Лендинг" in buttons(ask_service)

    await client.send("лендинг")  # текст вместо кнопки
    assert session.messages_to(CLIENT_ID)[-1].text == texts.ASK_SERVICE

    await client.click(ServiceCb(code="landing").pack())
    assert "шаг 4 из 4" in session.last_text_to(CLIENT_ID)

    await client.send("Нужен лендинг для кофейни, бюджет 40к")
    confirm = session.messages_to(CLIENT_ID)[-1]
    assert "Проверьте заявку" in confirm.text
    assert "Анна Смирнова" in confirm.text
    assert "+7 (900) 123-45-67" in confirm.text
    assert buttons(confirm) == [texts.BTN_SUBMIT, texts.BTN_EDIT, texts.BTN_CANCEL]

    session.clear()
    await client.click(FormCb(action="submit").pack())

    [lead] = await db.get_all_leads()
    assert (lead.name, lead.phone, lead.service) == ("Анна Смирнова", "+79001234567", "landing")
    assert lead.comment == "Нужен лендинг для кофейни, бюджет 40к"
    assert lead.user_id == CLIENT_ID and lead.username == "anna_demo"

    assert f"Заявка <b>№{lead.id}</b> принята" in session.last_text_to(CLIENT_ID)

    # мгновенное уведомление во все админ-чаты, с кнопками статуса
    for chat_id in (ADMIN_ID, ADMIN_GROUP_ID):
        card = session.messages_to(chat_id)[-1]
        assert f"Заявка №{lead.id}" in card.text
        assert "Нужен лендинг для кофейни" in card.text
        assert texts.LEAD_STATUSES["in_progress"] in buttons(card)


async def test_double_submit_creates_single_lead(client: TgClient, session: FakeSession, db: Database) -> None:
    await fill_form_until_confirm(client)
    await client.click(FormCb(action="submit").pack())
    await client.click(FormCb(action="submit").pack())
    assert len(await db.get_all_leads()) == 1
    assert session.of_type(AnswerCallbackQuery)[-1].text == texts.STALE_BUTTON


async def test_share_contact_and_name_from_profile(client: TgClient, session: FakeSession, db: Database) -> None:
    await client.click(MenuCb(section="apply").pack())
    await client.click(FormCb(action="use_tg_name").pack())
    assert "шаг 2 из 4" in session.last_text_to(CLIENT_ID)

    await client.send_contact("79007654321", user_id=999)  # чужой контакт
    assert "отправьте свой номер" in session.last_text_to(CLIENT_ID)

    await client.send_contact("79007654321")
    assert "шаг 3 из 4" in session.last_text_to(CLIENT_ID)

    await client.click(ServiceCb(code="tgbot").pack())
    await client.click(FormCb(action="skip_comment").pack())
    assert f"Комментарий: {texts.NO_COMMENT}" in session.last_text_to(CLIENT_ID)

    await client.click(FormCb(action="submit").pack())
    [lead] = await db.get_all_leads()
    assert (lead.name, lead.phone, lead.service, lead.comment) == ("Анна", "+79007654321", "tgbot", "")


async def test_edit_field_returns_to_confirm(client: TgClient, session: FakeSession, db: Database) -> None:
    await fill_form_until_confirm(client)

    await client.click(FormCb(action="edit").pack())
    edit_menu = session.of_type(EditMessageText)[-1]
    assert texts.ASK_EDIT_FIELD in edit_menu.text
    assert texts.BTN_EDIT_PHONE in buttons(edit_menu)

    await client.click(FormCb(action="back").pack())
    assert "Всё верно?" in session.of_type(EditMessageText)[-1].text

    await client.click(FormCb(action="edit").pack())
    await client.click(EditCb(field="phone").pack())
    assert "шаг 2 из 4" in session.last_text_to(CLIENT_ID)
    await client.send("+44 20 7946 0958")
    # после правки сразу экран подтверждения, а не шаг 3
    assert "Проверьте заявку" in session.last_text_to(CLIENT_ID)
    assert "+442079460958" in session.last_text_to(CLIENT_ID)

    await client.click(FormCb(action="edit").pack())
    await client.click(EditCb(field="service").pack())
    await client.click(ServiceCb(code="shop").pack())
    assert "Интернет-магазин" in session.last_text_to(CLIENT_ID)

    await client.click(FormCb(action="submit").pack())
    [lead] = await db.get_all_leads()
    assert (lead.phone, lead.service) == ("+442079460958", "shop")


@pytest.mark.parametrize("cancel", ["/cancel", "❌ Отмена", "отмена"])
async def test_cancel_by_text(client: TgClient, session: FakeSession, db: Database, cancel: str) -> None:
    await client.click(MenuCb(section="apply").pack())
    await client.send("Анна")
    await client.send(cancel)
    cancelled, menu = session.messages_to(CLIENT_ID)[-2:]
    assert cancelled.text == texts.LEAD_CANCELLED
    assert isinstance(cancelled.reply_markup, ReplyKeyboardRemove)
    assert texts.BTN_APPLY in buttons(menu)

    await client.send("+79001234567")  # анкета закрыта — номер больше не принимается
    assert session.last_text_to(CLIENT_ID) == texts.UNKNOWN
    assert await db.get_all_leads() == []


async def test_cancel_by_button_and_nothing_to_cancel(client: TgClient, session: FakeSession) -> None:
    await client.send("/cancel")
    assert session.last_text_to(CLIENT_ID) == texts.NOTHING_TO_CANCEL

    await fill_form_until_confirm(client)
    await client.click(FormCb(action="cancel").pack())
    assert texts.LEAD_CANCELLED in [m.text for m in session.messages_to(CLIENT_ID)[-2:]]


async def test_start_in_the_middle_of_form_resets_it(client: TgClient, session: FakeSession) -> None:
    await client.click(MenuCb(section="apply").pack())
    await client.send("Анна")
    await client.send("/start")
    cancelled, start = session.messages_to(CLIENT_ID)[-2:]
    assert cancelled.text == texts.LEAD_CANCELLED
    assert "Здравствуйте" in start.text


async def test_non_text_input_is_handled(client: TgClient, session: FakeSession) -> None:
    await client.click(MenuCb(section="apply").pack())
    await client.send_sticker()
    assert session.last_text_to(CLIENT_ID) == texts.NAME_NOT_TEXT
    await client.send("Анна")
    await client.send_sticker()
    assert "Не получилось распознать номер" in session.last_text_to(CLIENT_ID)


async def test_comment_too_long(client: TgClient, session: FakeSession) -> None:
    await fill_form_until_confirm(client, comment="x" * 1001)
    assert "слишком длинный" in session.last_text_to(CLIENT_ID)


async def test_stale_button_outside_form(client: TgClient, session: FakeSession) -> None:
    await client.click(ServiceCb(code="landing").pack())
    assert session.of_type(AnswerCallbackQuery)[-1].text == texts.STALE_BUTTON


async def test_cooldown_blocks_spam(config, db: Database, bot, session: FakeSession) -> None:
    dp = create_dispatcher(dataclasses.replace(config, lead_cooldown_minutes=10), db)
    from aiogram.types import User

    client = TgClient(dp, bot, User(id=CLIENT_ID, is_bot=False, first_name="Анна"))
    await fill_form_until_confirm(client)
    await client.click(FormCb(action="submit").pack())

    await client.click(MenuCb(section="apply").pack())
    assert "Новую заявку можно оставить через 10 мин" in session.last_text_to(CLIENT_ID)
    assert len(await db.get_all_leads()) == 1


# -- устойчивость к ошибкам --------------------------------------------------------------------


async def test_db_error_is_reported_and_form_is_kept(
    client: TgClient,
    session: FakeSession,
    db: Database,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await fill_form_until_confirm(client)

    original_add_lead = db.add_lead

    async def broken_add_lead(**kwargs):
        raise RuntimeError("disk I/O error")

    monkeypatch.setattr(db, "add_lead", broken_add_lead)
    with caplog.at_level(logging.ERROR):
        await client.click(FormCb(action="submit").pack())
    assert session.last_text_to(CLIENT_ID) == texts.ERROR_GENERIC
    assert "disk I/O error" in caplog.text

    # БД «починилась» — пользователь просто жмёт «Отправить» ещё раз, данные не потеряны
    monkeypatch.setattr(db, "add_lead", original_add_lead)
    await client.click(FormCb(action="submit").pack())
    [lead] = await db.get_all_leads()
    assert lead.name == "Анна"


async def test_admin_chat_failure_does_not_break_user_flow(
    client: TgClient, session: FakeSession, db: Database
) -> None:
    session.blocked_chats.add(ADMIN_GROUP_ID)  # бот удалён из админ-группы
    await fill_form_until_confirm(client)
    await client.click(FormCb(action="submit").pack())

    assert len(await db.get_all_leads()) == 1
    assert "принята" in session.last_text_to(CLIENT_ID)
    assert "Заявка №1" in session.last_text_to(ADMIN_ID)


async def test_user_blocking_bot_is_tracked(client: TgClient, dp, bot, db: Database) -> None:
    await client.send("/start")

    def member_update(old, new) -> Update:
        return Update(
            update_id=10_000,
            my_chat_member=ChatMemberUpdated(
                chat=client.chat,
                from_user=client.user,
                date=datetime.now(UTC),
                old_chat_member=old,
                new_chat_member=new,
            ),
        )

    await dp.feed_update(
        bot, member_update(ChatMemberMember(user=BOT_USER), ChatMemberBanned(user=BOT_USER, until_date=0))
    )
    assert await db.get_active_user_ids() == []

    await dp.feed_update(
        bot, member_update(ChatMemberBanned(user=BOT_USER, until_date=0), ChatMemberMember(user=BOT_USER))
    )
    assert await db.get_active_user_ids() == [CLIENT_ID]


async def test_restarting_form_removes_phone_keyboard(client: TgClient, session: FakeSession) -> None:
    await client.click(MenuCb(section="apply").pack())
    await client.send("Анна")
    assert isinstance(session.messages_to(CLIENT_ID)[-1].reply_markup, ReplyKeyboardMarkup)

    # посреди шага «телефон» клиент снова жмёт «Оставить заявку» в старом меню
    await client.click(MenuCb(section="apply").pack())
    restarted, ask_name = session.messages_to(CLIENT_ID)[-2:]
    assert restarted.text == texts.FORM_RESTARTED
    assert isinstance(restarted.reply_markup, ReplyKeyboardRemove)
    assert "шаг 1 из 4" in ask_name.text


async def test_service_keyboard_has_cancel_on_its_own_row(client: TgClient, session: FakeSession) -> None:
    await client.click(MenuCb(section="apply").pack())
    await client.send("Анна")
    await client.send("+79001234567")
    markup = session.messages_to(CLIENT_ID)[-1].reply_markup
    assert isinstance(markup, InlineKeyboardMarkup)
    assert [b.text for b in markup.inline_keyboard[-1]] == [texts.BTN_CANCEL]


async def test_expired_callback_query_still_works(client: TgClient, session: FakeSession, db: Database) -> None:
    """После простоя бота нажатия приходят «протухшими»: answerCallbackQuery падает, но действие выполняется."""
    await fill_form_until_confirm(client)
    session.raise_for[AnswerCallbackQuery] = lambda method: TelegramBadRequest(
        method=method, message="Bad Request: query is too old and response timeout expired or query ID is invalid"
    )
    await client.click(FormCb(action="submit").pack())
    assert len(await db.get_all_leads()) == 1
    assert "принята" in session.last_text_to(CLIENT_ID)
    assert texts.ERROR_GENERIC not in [m.text for m in session.messages_to(CLIENT_ID)]


async def test_admins_notified_even_if_client_reply_fails(client: TgClient, session: FakeSession, db: Database) -> None:
    await fill_form_until_confirm(client)

    def fail_client_confirmation(method: SendMessage) -> Exception | None:
        if method.chat_id == CLIENT_ID and "принята" in method.text:
            return TelegramNetworkError(method=method, message="Request timeout error")
        return None

    session.raise_for[SendMessage] = fail_client_confirmation
    await client.click(FormCb(action="submit").pack())
    [lead] = await db.get_all_leads()
    assert f"Заявка №{lead.id}" in session.last_text_to(ADMIN_ID)
    assert f"Заявка №{lead.id}" in session.last_text_to(ADMIN_GROUP_ID)
