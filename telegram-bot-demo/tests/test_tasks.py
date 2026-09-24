import asyncio

from bot.services import tasks


async def test_wait_all_waits_for_finished_work() -> None:
    done: list[int] = []

    async def job() -> None:
        await asyncio.sleep(0.01)
        done.append(1)

    tasks.spawn(job(), name="job")
    await tasks.wait_all()
    assert done == [1]


async def test_wait_all_cancels_after_grace_period() -> None:
    task = tasks.spawn(asyncio.sleep(10), name="slow")
    await tasks.wait_all(grace_seconds=0.01)
    assert task.cancelled()


async def test_wait_all_without_tasks_is_noop() -> None:
    await tasks.wait_all(grace_seconds=0)
