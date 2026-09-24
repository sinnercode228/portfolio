"""Хендлеры бота.

Каждый модуль экспортирует фабрику ``create_router()``: так роутеры не являются
глобальными синглтонами и в тестах можно собрать сколько угодно диспетчеров.

Порядок подключения важен: общие команды (/start, /cancel) обрабатываются раньше
анкеты, а «fallback» ловит всё, что не подошло остальным.
"""

from aiogram import Router

from bot.handlers import admin, common, errors, fallback, form, menu


def create_routers() -> list[Router]:
    return [
        errors.create_router(),
        common.create_router(),
        admin.create_router(),
        form.create_router(),
        menu.create_router(),
        fallback.create_router(),
    ]


__all__ = ["create_routers"]
