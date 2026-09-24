"""Фейковая сессия Telegram Bot API: бот «ходит в Telegram», не выходя в сеть.

Все запросы бота сохраняются в ``session.requests``, а ответы генерируются
локально. Так можно прогнать настоящие хендлеры aiogram целиком — без токена.
"""

from __future__ import annotations

import itertools
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import (
    CopyMessage,
    GetMe,
    SendDocument,
    SendMessage,
    TelegramMethod,
)
from aiogram.types import (
    CallbackQuery,
    Chat,
    Contact,
    Message,
    MessageId,
    Sticker,
    Update,
    User,
)

T = TypeVar("T")

BOT_USER = User(id=100500, is_bot=True, first_name="Demo", username="romashka_demo_bot")


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod[Any]] = []
        self.blocked_chats: set[int] = set()
        # тип метода -> фабрика исключения (вернёт None — запрос пройдёт успешно)
        self.raise_for: dict[type, Callable[[TelegramMethod[Any]], Exception | None]] = {}
        self._ids = itertools.count(1000)

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,  # noqa: ASYNC109 — сигнатура задана aiogram BaseSession
    ) -> Any:
        self.requests.append(method)
        chat_id = getattr(method, "chat_id", None)
        if chat_id in self.blocked_chats:
            raise TelegramForbiddenError(method=method, message="Forbidden: bot was blocked by the user")
        if type(method) in self.raise_for:
            error = self.raise_for[type(method)](method)
            if error is not None:
                raise error

        if isinstance(method, GetMe):
            return BOT_USER
        if isinstance(method, (SendMessage, SendDocument)):
            return Message(
                message_id=next(self._ids),
                date=datetime.now(UTC),
                chat=Chat(id=int(chat_id), type="private"),  # type: ignore[arg-type]
                from_user=BOT_USER,
                text=getattr(method, "text", None),
            )
        if isinstance(method, CopyMessage):
            return MessageId(message_id=next(self._ids))
        return True  # editMessageText, answerCallbackQuery, setMyCommands и т.п.

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:  # pragma: no cover
        yield b""

    async def close(self) -> None:
        pass

    # -- удобные выборки для проверок ------------------------------------------------

    def of_type(self, method_type: type[T]) -> list[T]:
        return [r for r in self.requests if isinstance(r, method_type)]

    def messages_to(self, chat_id: int) -> list[SendMessage]:
        return [r for r in self.of_type(SendMessage) if r.chat_id == chat_id]

    def last_text_to(self, chat_id: int) -> str:
        messages = self.messages_to(chat_id)
        assert messages, f"Боту не отправлено ни одного сообщения в чат {chat_id}"
        return messages[-1].text

    def clear(self) -> None:
        self.requests.clear()


class TgClient:
    """Имитирует действия пользователя: пишет текст, жмёт кнопки, делится контактом."""

    _update_ids = itertools.count(1)
    _message_ids = itertools.count(1)

    def __init__(self, dp: Dispatcher, bot: Bot, user: User, chat: Chat | None = None) -> None:
        self.dp = dp
        self.bot = bot
        self.user = user
        self.chat = chat or Chat(id=user.id, type="private")

    def _message(self, **kwargs: Any) -> Message:
        return Message(
            message_id=next(self._message_ids),
            date=datetime.now(UTC),
            chat=self.chat,
            from_user=self.user,
            **kwargs,
        )

    async def _feed(self, **update: Any) -> Any:
        return await self.dp.feed_update(self.bot, Update(update_id=next(self._update_ids), **update))

    async def send(self, text: str) -> Message:
        message = self._message(text=text)
        await self._feed(message=message)
        return message

    async def send_contact(self, phone: str, user_id: int | None = None) -> None:
        contact = Contact(phone_number=phone, first_name=self.user.first_name, user_id=user_id or self.user.id)
        await self._feed(message=self._message(contact=contact))

    async def send_sticker(self) -> None:
        """Сообщение без текста — проверяем, что анкета не падает и подсказывает, что делать."""
        sticker = Sticker(
            file_id="f", file_unique_id="u", type="regular", width=1, height=1, is_animated=False, is_video=False
        )
        await self._feed(message=self._message(sticker=sticker))

    async def click(self, callback_data: str) -> None:
        origin = Message(
            message_id=next(self._message_ids),
            date=datetime.now(UTC),
            chat=self.chat,
            from_user=BOT_USER,
            text="…",
        )
        callback = CallbackQuery(
            id=str(next(self._update_ids)),
            from_user=self.user,
            chat_instance="test",
            data=callback_data,
            message=origin,
        )
        await self._feed(callback_query=callback)
