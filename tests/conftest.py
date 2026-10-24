"""Общая подготовка для тестов.

Тесты не ходят в настоящий Telegram: вместо сети подставлена заглушка FakeSession,
которая запоминает, что бот пытался отправить. Так можно «нажимать кнопки»
и «писать сообщения» от имени разных пользователей и проверять ответы бота.
Каждый тест получает свою чистую базу данных во временной папке.
"""
import os
import sys
from datetime import datetime, timedelta
from itertools import count
from pathlib import Path

# Настройки должны появиться ДО импорта config — иначе он попробует прочитать .env
os.environ.update(BOT_TOKEN="123:test", MASTER_TG_ID="111", MASTER_USERNAME="demo_master", TIMEZONE="Europe/Moscow")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage  # noqa: E402
from aiogram.types import CallbackQuery, Chat, Message, Update, User  # noqa: E402

import config  # noqa: E402
import db  # noqa: E402
from handlers import client, master  # noqa: E402
from logic import availability  # noqa: E402
from logic.schedule import week_days, week_start  # noqa: E402

MASTER = User(id=111, is_bot=False, first_name="Master")
ANNA = User(id=501, is_bot=False, first_name="Anna", username="anna_tg")
BORIS = User(id=502, is_bot=False, first_name="Boris")

_ids = count(10_000)

# Роутер можно подключить только к одному диспетчеру, поэтому диспетчер общий на все тесты
_dp = Dispatcher()
_dp.include_router(master.router)
_dp.include_router(client.router)


class FakeSession(BaseSession):
    """Вместо отправки в Telegram просто запоминает запросы бота."""

    def __init__(self):
        super().__init__()
        self.calls = []

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, SendMessage):
            chat = Chat(id=method.chat_id, type="private")
            return Message(message_id=next(_ids), date=datetime.now(), chat=chat, text=method.text).as_(bot)
        return True

    async def close(self):
        pass

    async def stream_content(self, *args, **kwargs):
        yield b""


class Tg:
    """Удобные действия «от имени пользователя» и проверки того, что ответил бот."""

    def __init__(self):
        self.session = FakeSession()
        self.bot = Bot("123:test", session=self.session)
        self.dp = _dp

    @property
    def calls(self):
        return self.session.calls

    async def send(self, user: User, text: str | None = None, contact=None) -> None:
        message = Message(message_id=next(_ids), date=datetime.now(), chat=Chat(id=user.id, type="private"),
                          from_user=user, text=text, contact=contact)
        await self.dp.feed_update(self.bot, Update(update_id=next(_ids), message=message))

    async def press(self, user: User, data: str) -> None:
        message = Message(message_id=50, date=datetime.now(), chat=Chat(id=user.id, type="private"), text="old")
        query = CallbackQuery(id=str(next(_ids)), from_user=user, chat_instance="x", data=data, message=message)
        await self.dp.feed_update(self.bot, Update(update_id=next(_ids), callback_query=query))

    def screen(self) -> EditMessageText:
        """Последнее сообщение, которое бот изменил на месте."""
        return next(m for m in reversed(self.calls) if isinstance(m, EditMessageText))

    def buttons(self) -> list[tuple[str, str]]:
        """Кнопки на последнем изменённом сообщении: (текст, данные)."""
        return [(b.text, b.callback_data) for row in self.screen().reply_markup.inline_keyboard
                for b in row if b.callback_data]

    def sent_to(self, chat_id: int) -> list[SendMessage]:
        return [m for m in self.calls if isinstance(m, SendMessage) and m.chat_id == chat_id]

    def alert(self) -> str:
        return next(m for m in reversed(self.calls) if isinstance(m, AnswerCallbackQuery)).text

    def button(self, prefix: str, text_startswith: str = "") -> str:
        """Данные первой кнопки, у которой данные начинаются с prefix (и текст — с text_startswith)."""
        return next(cb for t, cb in self.buttons() if cb.startswith(prefix) and t.startswith(text_startswith))


@pytest.fixture
async def tg(tmp_path):
    """Чистая база с демо-данными, свежая память диалогов и бот-заглушка."""
    config.settings.db_path = str(tmp_path / "test.db")
    _dp.fsm.storage = MemoryStorage()
    await db.init_db()
    return Tg()


async def fill_schedule(weeks: int = 2, start_week: int = 0) -> None:
    """Заполняет расписание по демо-шаблону на несколько недель вперёд."""
    template = await db.get_template()
    monday = week_start(config.now().date()) + timedelta(weeks=start_week)
    days = [d for w in range(weeks) for d in week_days(monday + timedelta(weeks=w)) if d >= config.now().date()]
    await db.set_days({d: template[d.weekday()] for d in days})


def next_monday() -> datetime:
    """Понедельник следующей недели, 00:00 — удобная «точка» для записей в тестах."""
    monday = week_start(config.now().date()) + timedelta(weeks=1)
    return datetime.combine(monday, datetime.min.time())


async def book(user_id: int, service_id: int, start: datetime) -> int:
    """Запись напрямую через базу (как будто клиент прошёл весь путь)."""
    return await db.create_booking(
        user_id, service_id,
        start.strftime(config.DB_DATETIME_FORMAT),
        availability.horizon().strftime(config.DB_DATETIME_FORMAT),
    )
