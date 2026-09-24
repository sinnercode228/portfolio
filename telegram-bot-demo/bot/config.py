"""Конфигурация бота из переменных окружения / файла .env."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Формат токена BotFather: <числовой id бота>:<35 символов>
_TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{20,}$")
_PLACEHOLDER_TOKENS = frozenset({"", "123456789:replace-me-with-token-from-botfather"})
_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


class ConfigError(ValueError):
    """Понятная ошибка конфигурации (показывается пользователю при запуске)."""


@dataclass(frozen=True, slots=True)
class Config:
    bot_token: str = field(repr=False)
    admin_ids: frozenset[int] = frozenset()
    admin_chat_ids: tuple[int, ...] = ()
    db_path: Path = Path("data/leads.db")
    tz_name: str = "Europe/Moscow"
    log_level: str = "INFO"
    log_file: Path | None = None
    lead_cooldown_minutes: int = 5

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.tz_name)

    def is_admin(self, user_id: int | None) -> bool:
        return user_id is not None and user_id in self.admin_ids


def parse_ids(raw: str | None, var_name: str) -> tuple[int, ...]:
    """Разбирает список ID вида ``"123, 456;-100789"`` без дублей, с сохранением порядка."""
    if not raw or not raw.strip():
        return ()
    result: list[int] = []
    for part in re.split(r"[,;\s]+", raw.strip()):
        if not part:
            continue
        try:
            result.append(int(part))
        except ValueError:
            raise ConfigError(
                f"{var_name}: значение «{part}» не является числом. "
                "Укажите ID через запятую, например: 123456789,987654321"
            ) from None
    return tuple(dict.fromkeys(result))


def _parse_int(raw: str | None, var_name: str, default: int, *, minimum: int = 0) -> int:
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        raise ConfigError(f"{var_name}: ожидается целое число, получено «{raw}»") from None
    if value < minimum:
        raise ConfigError(f"{var_name}: значение должно быть не меньше {minimum}")
    return value


def load_config(env: Mapping[str, str] | None = None, *, dotenv_path: str | Path | None = None) -> Config:
    """Собирает :class:`Config`.

    Если ``env`` не передан — читает ``.env`` из текущей папки (или выше по дереву),
    не перезаписывая уже заданные переменные окружения, и берёт значения из ``os.environ``.
    """
    if env is None:
        from dotenv import find_dotenv, load_dotenv

        load_dotenv(dotenv_path or find_dotenv(usecwd=True))
        env = os.environ

    token = env.get("BOT_TOKEN", "").strip()
    if token in _PLACEHOLDER_TOKENS:
        raise ConfigError(
            "BOT_TOKEN не задан. Создайте бота у @BotFather, скопируйте токен "
            "и пропишите его в файл .env (см. .env.example)."
        )
    if not _TOKEN_RE.match(token):
        raise ConfigError("BOT_TOKEN выглядит некорректно. Ожидается формат 123456789:AAE...")

    admin_ids = parse_ids(env.get("ADMIN_IDS"), "ADMIN_IDS")
    admin_chat_ids = parse_ids(env.get("ADMIN_CHAT_IDS"), "ADMIN_CHAT_IDS") or admin_ids

    tz_name = env.get("TIMEZONE", "").strip() or "Europe/Moscow"
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ConfigError(f"TIMEZONE: неизвестный часовой пояс «{tz_name}». Пример: Europe/Moscow") from None

    log_level = (env.get("LOG_LEVEL", "").strip() or "INFO").upper()
    if log_level not in _LOG_LEVELS:
        raise ConfigError(f"LOG_LEVEL: допустимые значения — {', '.join(sorted(_LOG_LEVELS))}")

    log_file_raw = env.get("LOG_FILE", "").strip()

    return Config(
        bot_token=token,
        admin_ids=frozenset(admin_ids),
        admin_chat_ids=admin_chat_ids,
        db_path=Path(env.get("DB_PATH", "").strip() or "data/leads.db"),
        tz_name=tz_name,
        log_level=log_level,
        log_file=Path(log_file_raw) if log_file_raw else None,
        lead_cooldown_minutes=_parse_int(env.get("LEAD_COOLDOWN_MINUTES"), "LEAD_COOLDOWN_MINUTES", 5),
    )


def setup_logging(level: str = "INFO", log_file: Path | None = None) -> None:
    """Логи в stdout (удобно для Docker/journald) и, опционально, в файл с ротацией."""
    from logging.handlers import RotatingFileHandler

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=handlers,
        force=True,
    )
