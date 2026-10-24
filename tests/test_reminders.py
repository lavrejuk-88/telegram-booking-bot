"""Напоминания. Время «перематываем», передавая в reminders.check() нужный момент «сейчас»."""
from datetime import timedelta

import pytest

import db
import reminders
from config import DB_DATETIME_FORMAT, now
from keyboards.client import MyCb

F = DB_DATETIME_FORMAT


@pytest.fixture
async def clients(tg):
    """Четыре клиента; возвращает словарь tg_id → id в базе."""
    ids = {}
    for tg_id, name in ((501, "Анна"), (502, "Борис"), (503, "Вера"), (504, "Глеб")):
        await db.save_client(tg_id, None, name=name, phone="+7 900 000-00-00")
        ids[tg_id] = (await db.get_client(tg_id))["id"]
    return ids


async def make(client_id, start, created) -> int:
    """Запись напрямую в базу с нужной датой создания."""
    async with db.connect() as conn:
        cursor = await conn.execute(
            "INSERT INTO bookings (master_id, client_id, service_id, start_at, end_at, price, created_at)"
            " VALUES (1, ?, 2, ?, ?, 1500, ?)",
            (client_id, start.strftime(F), (start + timedelta(hours=1)).strftime(F), created.strftime(F)),
        )
        await conn.commit()
        return cursor.lastrowid


def visit_time():
    return now().replace(hour=14, minute=0) + timedelta(days=10)


def reminders_to(tg, chat_id):
    return [m for m in tg.sent_to(chat_id) if "⏰" in m.text]


async def test_day_and_hour_reminders_without_duplicates(tg, clients):
    visit = visit_time()
    booking_id = await make(clients[501], visit, created=visit - timedelta(days=5))

    await reminders.check(tg.bot, visit - timedelta(hours=25))
    assert not reminders_to(tg, 501)

    await reminders.check(tg.bot, visit - timedelta(hours=24))
    sent = reminders_to(tg, 501)
    assert len(sent) == 1 and "Завтра" in sent[0].text
    buttons = [b.callback_data for row in sent[0].reply_markup.inline_keyboard for b in row]
    assert MyCb(action="rs_days", id=booking_id).pack() in buttons
    assert MyCb(action="cancel", id=booking_id).pack() in buttons

    # повторные проверки (или перезапуск бота) не дублируют напоминание
    await reminders.check(tg.bot, visit - timedelta(hours=24))
    await reminders.check(tg.bot, visit - timedelta(hours=23, minutes=59))
    assert len(reminders_to(tg, 501)) == 1

    await reminders.check(tg.bot, visit - timedelta(hours=1))
    sent = reminders_to(tg, 501)
    assert len(sent) == 2 and "Через час" in sent[1].text


async def test_booked_less_than_a_day_before(tg, clients):
    visit = visit_time()
    await make(clients[502], visit, created=visit - timedelta(hours=5))
    await reminders.check(tg.bot, visit - timedelta(hours=4))
    await reminders.check(tg.bot, visit - timedelta(hours=1))
    sent = reminders_to(tg, 502)
    assert len(sent) == 1 and "Через час" in sent[0].text


async def test_booked_less_than_an_hour_before(tg, clients):
    visit = visit_time()
    await make(clients[503], visit, created=visit - timedelta(minutes=30))
    await reminders.check(tg.bot, visit - timedelta(minutes=29))
    assert not reminders_to(tg, 503)


async def test_bot_was_offline_only_hour_reminder(tg, clients):
    visit = visit_time()
    await make(clients[504], visit, created=visit - timedelta(days=3))
    await reminders.check(tg.bot, visit - timedelta(minutes=40))  # первая проверка после «простоя»
    sent = reminders_to(tg, 504)
    assert len(sent) == 1 and "Через час" in sent[0].text


async def test_cancelled_booking_not_reminded(tg, clients):
    visit = visit_time()
    booking_id = await make(clients[501], visit, created=visit - timedelta(days=5))
    await db.cancel_booking(booking_id, by="client")
    await reminders.check(tg.bot, visit - timedelta(hours=24))
    assert not reminders_to(tg, 501)
