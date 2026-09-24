from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from bot import texts
from bot.db import Stats
from bot.formatting import (
    TELEGRAM_MESSAGE_LIMIT,
    render_confirm,
    render_contacts,
    render_faq,
    render_help,
    render_lead_card,
    render_leads_list,
    render_prices,
    render_services,
    render_start,
    render_stats,
    render_summary,
    truncate,
)
from tests.test_export import make_lead

MSK = ZoneInfo("Europe/Moscow")


def test_start_escapes_name_and_has_demo_note() -> None:
    text = render_start("<script>")
    assert "&lt;script&gt;" in text and "<script>" not in text
    assert texts.BRAND in text
    assert "Демо-проект" in text
    assert "друг" in render_start(None)


def test_sections_contain_catalog() -> None:
    services = render_services()
    prices = render_prices()
    for service in texts.SERVICES.values():
        assert service.title in services
        assert service.price in prices
    assert all(q in render_faq() for q, _ in texts.FAQ)
    assert "Демо-проект" in render_contacts()


def test_help_shows_admin_commands_only_to_admin() -> None:
    assert "/leads" not in render_help(is_admin=False)
    assert "/leads" in render_help(is_admin=True)


def test_summary_and_confirm() -> None:
    data = {"name": "Анна", "phone": "+79001234567", "service": "tgbot", "comment": "Бот & <сайт>"}
    summary = render_summary(data)
    assert "Анна" in summary
    assert "+7 (900) 123-45-67" in summary
    assert "Telegram-бот" in summary
    assert "Бот &amp; &lt;сайт&gt;" in summary
    assert "Всё верно?" in render_confirm(data)

    no_comment = render_summary({**data, "comment": ""})
    assert f"Комментарий: {texts.NO_COMMENT}" in no_comment


def test_lead_card_escapes_user_input_and_links_profile() -> None:
    lead = make_lead(
        name="Анна",
        comment='<a href="http://phish.example">приз</a>',
        tg_full_name="<b>Hacker</b>",
        created_at=datetime(2026, 9, 24, 9, 30, tzinfo=UTC),
    )
    card = render_lead_card(lead, MSK)
    assert "Заявка №1" in card
    assert "24.09.2026 12:30" in card
    assert "+7 (900) 123-45-67" in card
    assert "Лендинг" in card
    assert "🆕 Новая" in card
    assert '<a href="http://phish.example">' not in card
    assert "&lt;a href=&quot;http://phish.example&quot;&gt;" in card
    assert '<a href="tg://user?id=555">&lt;b&gt;Hacker&lt;/b&gt;</a> (@anna_demo)' in card


def test_lead_card_without_username() -> None:
    card = render_lead_card(make_lead(username=None), MSK)
    assert "(id <code>555</code>)" in card


def test_unknown_service_code_is_shown_as_is() -> None:
    assert "legacy_service" in render_lead_card(make_lead(service="legacy_service"), MSK)


def test_leads_list() -> None:
    assert render_leads_list([], MSK) == texts.LEADS_EMPTY
    text = render_leads_list([make_lead(2, comment=""), make_lead(1)], MSK)
    assert text.index("№2") < text.index("№1")
    assert "Последние заявки</b> (2)" in text


def test_leads_list_fits_telegram_limit_in_worst_case() -> None:
    leads = [
        make_lead(i, name="Я" * 50, comment="длинный комментарий " * 60, service="support")
        for i in range(100_000, 100_010)
    ]
    assert len(render_leads_list(leads, MSK)) < TELEGRAM_MESSAGE_LIMIT


def test_truncate() -> None:
    assert truncate("коротко", 10) == "коротко"
    assert truncate("a  b\nc", 10) == "a b c"
    result = truncate("x" * 100, 10)
    assert len(result) == 10 and result.endswith("…")


def test_stats_rendering() -> None:
    stats = Stats(
        users_total=10,
        users_blocked=1,
        leads_total=4,
        leads_today=1,
        leads_week=3,
        unique_clients=3,
        by_service={"landing": 3, "shop": 1},
        by_status={"new": 2, "done": 2},
    )
    text = render_stats(stats)
    assert "Пользователей: <b>10</b>" in text
    assert "Конверсия в заявку: <b>30%</b>" in text
    assert "• Лендинг: 3" in text
    assert "• ✅ Закрыта: 2" in text

    empty = render_stats(Stats())
    assert "Конверсия в заявку: <b>0%</b>" in empty
