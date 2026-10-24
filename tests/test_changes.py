"""Перенос и отмена записи: клиентом («Моя запись») и специалистом («Записи»)."""
from datetime import timedelta

import db
from conftest import ANNA, MASTER, book, fill_schedule, next_monday
from keyboards.client import MyCb
from keyboards.master import MasterBookingCb


async def anna_booked(hour: int = 10, service_id: int = 2, day_offset: int = 0) -> int:
    await fill_schedule(weeks=2, start_week=1)
    await db.save_client(ANNA.id, ANNA.username, name="Анна", phone="+7 900 123-45-67")
    return await book(ANNA.id, service_id, next_monday().replace(hour=hour) + timedelta(days=day_offset))


async def test_reschedule_by_half_an_hour(tg):
    booking_id = await anna_booked()
    day = next_monday().date().isoformat()
    await tg.press(ANNA, "c:my_booking")
    assert "10:00–11:00" in tg.screen().text
    await tg.press(ANNA, MyCb(action="rs_day", id=booking_id, day=day).pack())
    times = [t for t, cb in tg.buttons() if cb.startswith("my:rs_time")]
    assert "10:00" not in times and "10:30" in times  # своё время не предлагаем, сдвиг «внахлёст» можно

    await tg.press(ANNA, MyCb(action="rs_ok", id=booking_id, day=day, n=630).pack())
    assert "перенесена" in tg.screen().text
    old = await db.get_booking_details(booking_id)
    new = await db.get_active_booking(ANNA.id)
    assert old["status"] == "rescheduled" and new["rescheduled_from"] == booking_id
    assert new["start_at"].endswith("10:30")
    note = tg.sent_to(111)[-1].text
    assert "перенёс" in note and "10:00" in note and "10:30" in note

    await tg.press(ANNA, MyCb(action="rs_ok", id=booking_id, day=day, n=720).pack())  # старая кнопка
    assert tg.alert() == "Эта запись уже неактивна"


async def test_reschedule_to_taken_time_keeps_booking(tg):
    booking_id = await anna_booked()
    await db.save_client(777, None, name="Борис", phone="+7 900 000-00-07")
    await book(777, 2, next_monday().replace(hour=12))
    try:
        await db.reschedule_booking(booking_id, ANNA.id, f"{next_monday().date()} 11:30", "2999-01-01 00:00")
        raise AssertionError("перенос на занятое время прошёл")
    except db.BookingError as error:
        assert error.code == "taken"
    assert (await db.get_booking_details(booking_id))["status"] == "active"


async def test_day_with_only_own_time_is_not_offered(tg):
    booking_id = await anna_booked(day_offset=2)
    wednesday = (next_monday() + timedelta(days=2)).date()
    await db.set_days({wednesday: [("10:00", "11:00")]})
    await tg.press(ANNA, MyCb(action="rs_days", id=booking_id).pack())
    assert not any(wednesday.isoformat() in cb for _, cb in tg.buttons())


async def test_client_cancels(tg):
    booking_id = await anna_booked()
    await tg.press(ANNA, MyCb(action="cancel", id=booking_id).pack())
    assert "Точно отменить" in tg.screen().text
    await tg.press(ANNA, MyCb(action="cancel_ok", id=booking_id).pack())
    assert "отменена" in tg.screen().text
    assert (await db.get_booking_details(booking_id))["cancelled_by"] == "client"
    assert "Клиент отменил" in tg.sent_to(111)[-1].text
    await tg.send(ANNA, "/start")
    assert "Моя запись" not in str(tg.sent_to(ANNA.id)[-1].reply_markup)


async def test_master_list_and_cancel_with_reason(tg):
    booking_id = await anna_booked(hour=15, service_id=3, day_offset=1)
    await tg.press(MASTER, MasterBookingCb(action="list", f="all").pack())
    assert "Комплекс" in tg.screen().text and "Анна" in tg.screen().text
    await tg.press(MASTER, MasterBookingCb(action="open", id=booking_id, f="all").pack())
    assert "+7 900 123-45-67" in tg.screen().text

    await tg.press(MASTER, MasterBookingCb(action="cancel", id=booking_id, f="all").pack())
    await tg.send(MASTER, "Заболел, извините")
    booking = await db.get_booking_details(booking_id)
    assert (booking["status"], booking["cancelled_by"], booking["cancel_reason"]) == ("cancelled", "master", "Заболел, извините")
    message = tg.sent_to(ANNA.id)[-1]
    assert "Мастер отменил" in message.text and "Заболел" in message.text
    assert "Записаться снова" in str(message.reply_markup)


async def test_master_cancel_without_reason(tg):
    booking_id = await anna_booked()
    await tg.press(MASTER, MasterBookingCb(action="cancel", id=booking_id, f="all").pack())
    await tg.press(MASTER, MasterBookingCb(action="nocause", id=booking_id, f="all").pack())
    assert (await db.get_booking_details(booking_id))["status"] == "cancelled"
    assert "Причина" not in tg.sent_to(ANNA.id)[-1].text
