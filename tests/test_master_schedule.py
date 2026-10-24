"""Раздел «Расписание» у специалиста, включая защиту записей клиентов."""
from datetime import timedelta

import db
from config import now
from conftest import ANNA, MASTER, book, next_monday
from keyboards.master import SchedCb
from logic.schedule import week_days, week_start


async def test_week_view_and_navigation(tg):
    await tg.press(MASTER, "m:schedule")
    labels = [t for t, _ in tg.buttons()]
    assert "Ваше расписание" in tg.screen().text
    assert not any(t.startswith("◀️") for t in labels)  # в прошлое листать нельзя
    monday = week_start(now().date())
    await tg.press(MASTER, SchedCb(action="week", day=monday.isoformat(), n=1).pack())
    labels = [t for t, _ in tg.buttons()]
    assert any(t.startswith("◀️") for t in labels) and any("текущей неделе" in t for t in labels)


async def test_day_editor_save_and_cancel(tg):
    today = now().date()
    await tg.press(MASTER, SchedCb(action="day", day=today.isoformat()).pack())
    for hour in (10, 11, 13):
        await tg.press(MASTER, SchedCb(action="hour", n=hour).pack())
    assert "10:00–12:00, 13:00–14:00" in tg.screen().text
    await tg.press(MASTER, SchedCb(action="hour", n=13).pack())
    await tg.press(MASTER, SchedCb(action="save").pack())
    assert (await db.get_intervals(today, today))[today] == [("10:00", "12:00")]

    await tg.press(MASTER, SchedCb(action="day", day=today.isoformat()).pack())
    await tg.press(MASTER, SchedCb(action="hour", n=20).pack())
    await tg.press(MASTER, SchedCb(action="cancel").pack())
    assert (await db.get_intervals(today, today))[today] == [("10:00", "12:00")]

    await tg.press(MASTER, SchedCb(action="hour", n=9).pack())  # кнопка из закрытого редактора
    assert "устарела" in tg.alert()


async def test_past_day_is_locked(tg):
    yesterday = now().date() - timedelta(days=1)
    await tg.press(MASTER, SchedCb(action="day", day=yesterday.isoformat()).pack())
    assert "уже прошёл" in tg.alert()


async def test_apply_template_copy_and_clear(tg):
    nxt = next_monday().date()
    template = await db.get_template()
    await tg.press(MASTER, SchedCb(action="do", day=nxt.isoformat(), op="apply").pack())
    week = await db.get_intervals(nxt, nxt + timedelta(days=6))
    assert all(week[d] == template[d.weekday()] for d in week)

    await tg.press(MASTER, SchedCb(action="do", day=nxt.isoformat(), op="copy").pack())
    after = nxt + timedelta(weeks=1)
    assert await db.get_intervals(after, after + timedelta(days=6)) == {d + timedelta(weeks=1): v for d, v in week.items()}

    await tg.press(MASTER, SchedCb(action="do", day=after.isoformat(), op="clear").pack())
    assert all(v == [] for v in (await db.get_intervals(after, after + timedelta(days=6))).values())


async def test_template_day_edit(tg):
    await tg.press(MASTER, SchedCb(action="tpl_day", n=6).pack())
    assert "воскресенье" in tg.screen().text
    await tg.press(MASTER, SchedCb(action="hour", n=12).pack())
    await tg.press(MASTER, SchedCb(action="hour", n=13).pack())
    await tg.press(MASTER, SchedCb(action="save").pack())
    assert (await db.get_template())[6] == [("12:00", "14:00")]


async def test_old_button_for_past_week_does_not_crash(tg):
    old = week_start(now().date()) - timedelta(weeks=2)
    await tg.press(MASTER, SchedCb(action="do", day=old.isoformat(), op="clear").pack())
    assert "Ваше расписание" in tg.screen().text


async def _week_with_booking(tg):
    monday = next_monday()
    template = await db.get_template()
    await db.set_days({d: template[d.weekday()] for d in week_days(monday.date())})
    await db.save_client(ANNA.id, ANNA.username, name="Анна", phone="+7 900 123-45-67")
    tuesday = monday + timedelta(days=1)
    booking_id = await book(ANNA.id, 3, tuesday.replace(hour=12, minute=30))  # 12:30–14:00
    return monday.date(), tuesday.date(), booking_id, template


async def test_conflict_abort(tg):
    monday, tuesday, _, template = await _week_with_booking(tg)
    await tg.press(MASTER, SchedCb(action="do", day=monday.isoformat(), op="clear").pack())
    assert "уже записаны" in tg.screen().text and "Анна" in tg.screen().text
    await tg.press(MASTER, SchedCb(action="conf", op="abort").pack())
    assert (await db.get_intervals(tuesday, tuesday))[tuesday] == template[tuesday.weekday()]


async def test_conflict_keep_booking_hours(tg):
    monday, tuesday, booking_id, _ = await _week_with_booking(tg)
    await tg.press(MASTER, SchedCb(action="do", day=monday.isoformat(), op="clear").pack())
    await tg.press(MASTER, SchedCb(action="conf", op="keep").pack())
    week = await db.get_intervals(monday, monday + timedelta(days=6))
    assert week[tuesday] == [("12:00", "14:00")] and week[monday] == []
    assert (await db.get_booking_details(booking_id))["status"] == "active"


async def test_conflict_cancel_and_notify(tg):
    _, tuesday, booking_id, _ = await _week_with_booking(tg)
    await tg.press(MASTER, SchedCb(action="day", day=tuesday.isoformat()).pack())
    await tg.press(MASTER, SchedCb(action="off").pack())
    await tg.press(MASTER, SchedCb(action="conf", op="cancel").pack())
    assert "Записей отменено: 1" in tg.screen().text
    assert (await db.get_booking_details(booking_id))["status"] == "cancelled"
    assert "изменилось расписание" in tg.sent_to(ANNA.id)[-1].text


async def test_no_conflict_saves_immediately(tg):
    await tg.press(MASTER, SchedCb(action="do", day=next_monday().date().isoformat(), op="apply").pack())
    assert "заполнена по шаблону" in tg.screen().text
