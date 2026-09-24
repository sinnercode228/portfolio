"""Фоновые задачи (например, рассылка), которые не должны блокировать обработку апдейтов."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)

# Держим ссылки на задачи, иначе сборщик мусора может прервать их на середине.
_tasks: set[asyncio.Task[Any]] = set()


def spawn(coro: Coroutine[Any, Any, Any], *, name: str) -> asyncio.Task[Any]:
    task = asyncio.create_task(coro, name=name)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


async def wait_all(grace_seconds: float | None = None) -> None:
    """Дожидается фоновых задач; по истечении ``grace_seconds`` отменяет оставшиеся."""
    if not _tasks:
        return
    pending = list(_tasks)
    logger.info("Ожидаю завершения фоновых задач: %s", len(pending))
    _, still_running = await asyncio.wait(pending, timeout=grace_seconds)
    for task in still_running:
        logger.warning("Фоновая задача %s прервана при остановке", task.get_name())
        task.cancel()
    if still_running:
        await asyncio.gather(*still_running, return_exceptions=True)
