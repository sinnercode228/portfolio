from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from bot.db import SCHEMA_VERSION, Database

MSK = ZoneInfo("Europe/Moscow")


async def add(db: Database, user_id: int = 1, *, service: str = "landing", now: datetime | None = None, **kw):
    return await db.add_lead(
        user_id=user_id,
        username=kw.get("username", "user"),
        tg_full_name=kw.get("tg_full_name", "Test User"),
        name=kw.get("name", "Анна"),
        phone=kw.get("phone", "+79001234567"),
        service=service,
        comment=kw.get("comment", ""),
        now=now,
    )


async def test_schema_is_created_and_versioned(db: Database) -> None:
    async with db.conn.execute("PRAGMA user_version") as cur:
        assert (await cur.fetchone())[0] == SCHEMA_VERSION
    # повторное подключение к той же БД не ломает данные
    await add(db)
    await db.close()
    await db.connect()
    assert len(await db.get_all_leads()) == 1


async def test_add_and_get_lead(db: Database) -> None:
    lead = await add(db, user_id=42, comment="Нужен сайт", name="Иван")
    assert lead.id == 1
    assert lead.status == "new"
    assert lead.created_at.tzinfo is not None
    fetched = await db.get_lead(lead.id)
    assert fetched == lead
    assert await db.get_lead(999) is None


async def test_last_leads_order_and_limit(db: Database) -> None:
    for i in range(15):
        await add(db, user_id=i)
    last = await db.get_last_leads(10)
    assert [lead.id for lead in last] == list(range(15, 5, -1))
    assert [lead.id for lead in await db.get_all_leads()] == list(range(1, 16))


async def test_set_lead_status(db: Database) -> None:
    lead = await add(db)
    updated = await db.set_lead_status(lead.id, "in_progress")
    assert updated is not None and updated.status == "in_progress"
    assert await db.set_lead_status(999, "done") is None
    with pytest.raises(ValueError):
        await db.set_lead_status(lead.id, "hacked")


async def test_users_upsert_block_and_recipients(db: Database) -> None:
    await db.upsert_user(1, "a", "A")
    await db.upsert_user(2, "b", "B")
    await db.upsert_user(3, None, "C")
    await db.set_user_blocked(2, True)
    assert await db.get_active_user_ids() == [1, 3]

    # пользователь вернулся (/start) — снова получает рассылки, данные обновились
    await db.upsert_user(2, "b_new", "B New")
    assert await db.get_active_user_ids() == [1, 2, 3]
    async with db.conn.execute("SELECT username FROM users WHERE user_id = 2") as cur:
        assert (await cur.fetchone())[0] == "b_new"


async def test_last_lead_time(db: Database) -> None:
    assert await db.last_lead_time(1) is None
    t1 = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 9, 2, 10, 0, tzinfo=UTC)
    await add(db, user_id=1, now=t1)
    await add(db, user_id=1, now=t2)
    await add(db, user_id=2, now=t2 + timedelta(days=1))
    assert await db.last_lead_time(1) == t2


async def test_naive_datetime_is_rejected(db: Database) -> None:
    with pytest.raises(ValueError):
        await add(db, now=datetime(2026, 1, 1))


async def test_stats(db: Database) -> None:
    now = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)  # 15:00 по Москве
    for uid in (1, 2, 3, 4):
        await db.upsert_user(uid, None, f"U{uid}")
    await db.set_user_blocked(4, True)

    await add(db, 1, service="landing", now=now - timedelta(hours=1))  # сегодня
    await add(db, 1, service="shop", now=now - timedelta(hours=14))  # 01:00 МСК — всё ещё сегодня
    await add(db, 2, service="landing", now=now - timedelta(hours=16))  # вчера по МСК
    await add(db, 3, service="landing", now=now - timedelta(days=10))  # старше недели
    await db.set_lead_status(1, "done")

    stats = await db.get_stats(MSK, now=now)
    assert stats.users_total == 4
    assert stats.users_blocked == 1
    assert stats.leads_total == 4
    assert stats.leads_today == 2
    assert stats.leads_week == 3
    assert stats.unique_clients == 3
    assert stats.by_service == {"landing": 3, "shop": 1}
    assert stats.by_status == {"new": 3, "done": 1}
    assert stats.conversion == pytest.approx(0.75)


async def test_stats_empty(db: Database) -> None:
    stats = await db.get_stats(MSK)
    assert stats.leads_total == 0
    assert stats.conversion == 0.0
    assert stats.by_service == {}


async def test_not_connected_raises(tmp_path) -> None:
    db = Database(tmp_path / "x.db")
    with pytest.raises(RuntimeError, match="не подключена"):
        await db.get_all_leads()


async def test_context_manager_and_memory_db() -> None:
    async with Database(":memory:") as db:
        await add(db)
        assert len(await db.get_all_leads()) == 1
    assert db._conn is None
