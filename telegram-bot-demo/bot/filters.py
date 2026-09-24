"""Пользовательские фильтры aiogram."""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from bot.config import Config


class IsAdmin(BaseFilter):
    """Пропускает только пользователей из ADMIN_IDS.

    ``config`` приходит из workflow_data диспетчера (dp["config"]).
    """

    async def __call__(self, event: Message | CallbackQuery, config: Config) -> bool:
        user = event.from_user
        return user is not None and config.is_admin(user.id)
