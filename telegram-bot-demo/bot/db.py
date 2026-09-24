"""Слой хранения: SQLite через aiosqlite.

Все даты хранятся в UTC в ISO-формате (``2026-09-24T10:15:00+00:00``),
поэтому их можно сравнивать как строки. Перевод в локальное время — только при выводе.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta, tzinfo
from pathlib import Path
from types import TracebackType
from typing import Self

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY,
    username      TEXT,
    full_name     TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL,
    last_seen_at  TEXT    NOT NULL,
    is_blocked    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS leads (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    username      TEXT,
    tg_full_name  TEXT    NOT NULL DEFAULT '',
    name          TEXT    NOT NULL,
    phone         TEXT    NOT NULL,
    service       TEXT    NOT NULL,
    comment       TEXT    NOT NULL DEFAULT '',
    status        TEXT    NOT NULL DEFAULT 'new',
    created_at    TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads (created_at);
CREATE INDEX IF NOT EXISTS idx_leads_user ON leads (user_id, created_at);
"""

LEAD_STATUSES = ("new", "in_progress", "done", "rejected")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _to_db(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("Ожидается datetime с часовым поясом (aware)")
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def _from_db(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass(frozen=True, slots=True)
class Lead:
    id: int
    user_id: int
    username: str | None
    tg_full_name: str
    name: str
    phone: str
    service: str
    comment: str
    status: str
    created_at: datetime

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> Lead:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            username=row["username"],
            tg_full_name=row["tg_full_name"],
            name=row["name"],
            phone=row["phone"],
            service=row["service"],
            comment=row["comment"],
            status=row["status"],
            created_at=_from_db(row["created_at"]),
        )


@dataclass(frozen=True, slots=True)
class Stats:
    users_total: int = 0
    users_blocked: int = 0
    leads_total: int = 0
    leads_today: int = 0
    leads_week: int = 0
    unique_clients: int = 0
    by_service: dict[str, int] = field(default_factory=dict)
    by_status: dict[str, int] = field(default_factory=dict)

    @property
    def conversion(self) -> float:
        """Доля пользователей, оставивших хотя бы одну заявку (0..1)."""
        if not self.users_total:
            return 0.0
        return min(self.unique_clients / self.users_total, 1.0)


class Database:
    """Тонкая асинхронная обёртка над SQLite с одним долгоживущим соединением."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._conn: aiosqlite.Connection | None = None

    # -- lifecycle -----------------------------------------------------------

    async def connect(self) -> None:
        if self._conn is not None:
            return
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA busy_timeout=5000")
        await self._migrate()
        logger.info("База данных подключена: %s", self.path)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            logger.info("База данных закрыта")

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("База данных не подключена: вызовите await db.connect()")
        return self._conn

    async def _migrate(self) -> None:
        async with self.conn.execute("PRAGMA user_version") as cur:
            row = await cur.fetchone()
        version = row[0] if row else 0
        if version < SCHEMA_VERSION:
            await self.conn.executescript(_SCHEMA)
            await self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            await self.conn.commit()
            logger.info("Схема БД обновлена до версии %s", SCHEMA_VERSION)

    # -- users ---------------------------------------------------------------

    async def upsert_user(
        self,
        user_id: int,
        username: str | None,
        full_name: str,
        *,
        now: datetime | None = None,
    ) -> None:
        """Добавляет пользователя или обновляет его данные; снимает флаг блокировки."""
        ts = _to_db(now or _utc_now())
        await self.conn.execute(
            """
            INSERT INTO users (user_id, username, full_name, created_at, last_seen_at, is_blocked)
            VALUES (?, ?, ?, ?, ?, 0)
            ON CONFLICT (user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                last_seen_at = excluded.last_seen_at,
                is_blocked = 0
            """,
            (user_id, username, full_name, ts, ts),
        )
        await self.conn.commit()

    async def set_user_blocked(self, user_id: int, blocked: bool = True) -> None:
        await self.conn.execute(
            "UPDATE users SET is_blocked = ? WHERE user_id = ?",
            (int(blocked), user_id),
        )
        await self.conn.commit()

    async def get_active_user_ids(self) -> list[int]:
        async with self.conn.execute("SELECT user_id FROM users WHERE is_blocked = 0 ORDER BY user_id") as cur:
            return [row[0] for row in await cur.fetchall()]

    # -- leads ---------------------------------------------------------------

    async def add_lead(
        self,
        *,
        user_id: int,
        username: str | None,
        tg_full_name: str,
        name: str,
        phone: str,
        service: str,
        comment: str = "",
        now: datetime | None = None,
    ) -> Lead:
        created_at = now or _utc_now()
        cur = await self.conn.execute(
            """
            INSERT INTO leads (user_id, username, tg_full_name, name, phone, service, comment, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?)
            """,
            (user_id, username, tg_full_name, name, phone, service, comment, _to_db(created_at)),
        )
        await self.conn.commit()
        lead_id = cur.lastrowid
        await cur.close()
        assert lead_id is not None
        lead = await self.get_lead(lead_id)
        assert lead is not None
        return lead

    async def get_lead(self, lead_id: int) -> Lead | None:
        async with self.conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)) as cur:
            row = await cur.fetchone()
        return Lead.from_row(row) if row else None

    async def get_last_leads(self, limit: int = 10) -> list[Lead]:
        """Последние ``limit`` заявок, от новых к старым."""
        async with self.conn.execute("SELECT * FROM leads ORDER BY id DESC LIMIT ?", (limit,)) as cur:
            return [Lead.from_row(row) for row in await cur.fetchall()]

    async def get_all_leads(self) -> list[Lead]:
        """Все заявки в хронологическом порядке (для экспорта)."""
        async with self.conn.execute("SELECT * FROM leads ORDER BY id ASC") as cur:
            return [Lead.from_row(row) for row in await cur.fetchall()]

    async def set_lead_status(self, lead_id: int, status: str) -> Lead | None:
        if status not in LEAD_STATUSES:
            raise ValueError(f"Неизвестный статус заявки: {status!r}")
        await self.conn.execute("UPDATE leads SET status = ? WHERE id = ?", (status, lead_id))
        await self.conn.commit()
        return await self.get_lead(lead_id)

    async def last_lead_time(self, user_id: int) -> datetime | None:
        async with self.conn.execute("SELECT MAX(created_at) FROM leads WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        return _from_db(row[0]) if row and row[0] else None

    # -- stats ---------------------------------------------------------------

    async def get_stats(self, tz: tzinfo, *, now: datetime | None = None) -> Stats:
        now = now or _utc_now()
        local_midnight = datetime.combine(now.astimezone(tz).date(), time.min, tzinfo=tz)
        today_start = _to_db(local_midnight)
        week_start = _to_db(local_midnight - timedelta(days=6))  # сегодня + 6 предыдущих дней

        async def scalar(sql: str, params: tuple[object, ...] = ()) -> int:
            async with self.conn.execute(sql, params) as cur:
                row = await cur.fetchone()
            return int(row[0] or 0) if row else 0

        async def grouped(column: str) -> dict[str, int]:
            async with self.conn.execute(
                f"SELECT {column}, COUNT(*) AS n FROM leads GROUP BY {column} ORDER BY n DESC, {column}"
            ) as cur:
                return {row[0]: row[1] for row in await cur.fetchall()}

        return Stats(
            users_total=await scalar("SELECT COUNT(*) FROM users"),
            users_blocked=await scalar("SELECT COUNT(*) FROM users WHERE is_blocked = 1"),
            leads_total=await scalar("SELECT COUNT(*) FROM leads"),
            leads_today=await scalar("SELECT COUNT(*) FROM leads WHERE created_at >= ?", (today_start,)),
            leads_week=await scalar("SELECT COUNT(*) FROM leads WHERE created_at >= ?", (week_start,)),
            unique_clients=await scalar("SELECT COUNT(DISTINCT user_id) FROM leads"),
            by_service=await grouped("service"),
            by_status=await grouped("status"),
        )
