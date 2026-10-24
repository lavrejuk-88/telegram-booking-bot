"""Запись клиента: путь «услуга → день → время → карточка → Записаться», защита от двойной записи."""
import asyncio
from datetime import datetime, timedelta

from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import DeleteMessage, SendMessage
from aiogram.types import Contact, ReplyKeyboardMarkup, ReplyKeyboardRemove

import db
from config import DB_DATETIME_FORMAT
from conftest import ANNA, BORIS, book, fill_schedule, next_monday
from keyboards.client import BookCb
from logic import availability


async def open_first_time(tg, user, service_title="Стандарт"):
    """Проходит путь до карточки: меню → услуга → первый день → первое время."""
    await tg.press(user, "c:book")
    await tg.press(user, tg.button("bk:days", service_title))
    await tg.press(user, tg.button("bk:day"))
    time_text, time_cb = next((t, cb) for t, cb in tg.buttons() if cb.startswith("bk:time"))
    await tg.press(user, time_cb)
    return time_text, time_cb


async def test_full_booking_path_for_new_client(tg):
    await fill_schedule()
    _, time_cb = await open_first_time(tg, ANNA)
    assert "Ваша запись" in tg.screen().text and "(МСК, UTC+3)" in tg.screen().text
    assert "Как вас зовут" in tg.sent_to(ANNA.id)[-1].text

    await tg.send(ANNA, "1")
    assert "⚠️" in tg.screen().text  # подсказка в том же вопросе
    await tg.send(ANNA, "  Анна  ")
    assert (await db.get_client(ANNA.id))["name"] == "Анна"
    ask_phone = tg.sent_to(ANNA.id)[-1]
    assert isinstance(ask_phone.reply_markup, ReplyKeyboardMarkup)

    await tg.send(ANNA, contact=Contact(phone_number="79990000000", first_name="X", user_id=999))
    assert "чужой контакт" in tg.screen().text
    await tg.send(ANNA, contact=Contact(phone_number="79001234567", first_name="Anna", user_id=ANNA.id))
    assert (await db.get_client(ANNA.id))["phone"] == "+7 900 123-45-67"
    assert any(isinstance(c, SendMessage) and isinstance(c.reply_markup, ReplyKeyboardRemove) for c in tg.calls[-6:])

    await tg.press(ANNA, tg.button("bk:confirm"))
    assert "Вы записаны" in tg.screen().text
    booking = await db.get_active_booking(ANNA.id)
    assert booking["service_title"] == "Стандарт" and booking["price"] == 1500

    note = tg.sent_to(111)[-1]
    assert "Новая запись" in note.text and "Анна" in note.text and "@anna_tg" in note.text
    assert note.reply_markup.inline_keyboard[0][0].url == "https://t.me/anna_tg"


async def test_only_one_active_booking(tg):
    await fill_schedule()
    await db.save_client(ANNA.id, None, name="Анна", phone="+7 900 123-45-67")
    await book(ANNA.id, 2, next_monday().replace(hour=10))
    await tg.press(ANNA, "c:book")
    assert "уже есть запись" in tg.screen().text
    await tg.send(ANNA, "/start")
    assert "Моя запись" in str(tg.sent_to(ANNA.id)[-1].reply_markup)


async def test_taken_time_is_not_offered_and_old_button_fails(tg):
    await fill_schedule()
    await db.save_client(ANNA.id, None, name="Анна", phone="+7 900 123-45-67")
    time_text, time_cb = await open_first_time(tg, BORIS)
    data = BookCb.unpack(time_cb)
    await book(ANNA.id, data.id, datetime.fromisoformat(data.day) + timedelta(minutes=data.n))

    await tg.press(BORIS, BookCb(action="day", id=data.id, day=data.day).pack())
    assert time_text not in [t for t, cb in tg.buttons() if cb.startswith("bk:time")]
    await tg.press(BORIS, time_cb)
    assert tg.alert() == "Это время уже заняли"


async def test_longer_service_does_not_overlap(tg):
    await fill_schedule()
    await db.save_client(ANNA.id, None, name="Анна", phone="+7 900 123-45-67")
    start = next_monday().replace(hour=12)
    await book(ANNA.id, 2, start)  # 12:00–13:00
    free = (await availability.free_times(90, start.date(), start.date()))[start.date()]
    assert all(not (s < start + timedelta(minutes=60) and start < s + timedelta(minutes=90)) for s in free)


async def test_race_two_clients_same_time(tg):
    await fill_schedule()
    await db.save_client(601, None, name="Клиент 1", phone="+7 900 000-00-01")
    await db.save_client(602, None, name="Клиент 2", phone="+7 900 000-00-02")
    start = next_monday().replace(hour=10).strftime(DB_DATETIME_FORMAT)
    horizon = availability.horizon().strftime(DB_DATETIME_FORMAT)
    results = await asyncio.gather(
        db.create_booking(601, 2, start, horizon), db.create_booking(602, 2, start, horizon), return_exceptions=True
    )
    assert sum(isinstance(r, int) for r in results) == 1
    assert [r.code for r in results if isinstance(r, db.BookingError)] == ["taken"]


async def test_outside_working_hours_rejected(tg):
    await fill_schedule()
    await db.save_client(601, None, name="Клиент", phone="+7 900 000-00-01")
    try:
        await book(601, 2, next_monday().replace(hour=6))
        raise AssertionError("запись вне рабочего времени прошла")
    except db.BookingError as error:
        assert error.code == "taken"


async def test_returning_client_skips_questions(tg):
    await fill_schedule()
    await db.save_client(BORIS.id, None, name="Борис", phone="+7 900 555-55-55")
    sent_before = len(tg.sent_to(BORIS.id))
    await open_first_time(tg, BORIS)
    assert "Имя: Борис" in tg.screen().text and "Заполните" not in tg.screen().text
    assert len(tg.sent_to(BORIS.id)) == sent_before  # вопросов не было


async def test_booking_saved_even_if_master_blocked_bot(tg):
    await fill_schedule()
    await db.save_client(BORIS.id, None, name="Борис", phone="+7 900 555-55-55")
    await open_first_time(tg, BORIS)
    original = tg.session.make_request

    async def failing(bot, method, timeout=None):
        if isinstance(method, SendMessage) and method.chat_id == 111:
            raise TelegramForbiddenError(method=method, message="bot was blocked by the user")
        return await original(bot, method, timeout)

    tg.session.make_request = failing
    await tg.press(BORIS, tg.button("bk:confirm"))
    assert "Вы записаны" in tg.screen().text
    assert await db.get_active_booking(BORIS.id) is not None


async def test_hidden_service_is_not_bookable(tg):
    await db.toggle_service(1)
    await tg.press(BORIS, BookCb(action="days", id=1).pack())
    assert "недоступна" in tg.screen().text


async def test_service_hidden_while_entering_phone(tg):
    await fill_schedule()
    await db.save_client(BORIS.id, None, name="Борис")
    await open_first_time(tg, BORIS)
    await db.toggle_service(2)
    await tg.send(BORIS, "89001234567")
    assert "недоступна" in tg.screen().text
    assert (await db.get_client(BORIS.id))["phone"] == "+7 900 123-45-67"


async def test_start_during_phone_question_cleans_up(tg):
    await fill_schedule()
    await db.save_client(BORIS.id, None, name="Борис")
    await open_first_time(tg, BORIS)
    assert isinstance(tg.sent_to(BORIS.id)[-1].reply_markup, ReplyKeyboardMarkup)
    before = len(tg.calls)
    await tg.send(BORIS, "/start")
    tail = tg.calls[before:]
    assert any(isinstance(m, SendMessage) and isinstance(m.reply_markup, ReplyKeyboardRemove) for m in tail)
    assert sum(isinstance(m, DeleteMessage) for m in tail) >= 2  # вопрос и служебное сообщение
