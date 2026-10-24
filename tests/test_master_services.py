"""Раздел «Услуги» у специалиста."""
from aiogram.methods import AnswerCallbackQuery, DeleteMessage

import db
from conftest import ANNA, BORIS, MASTER, book, fill_schedule, next_monday
from keyboards.client import BookCb
from keyboards.master import ServiceCb


async def test_add_service_in_four_steps(tg):
    await tg.press(MASTER, "m:services")
    await tg.press(MASTER, ServiceCb(action="add").pack())
    assert "шаг 1 из 4" in tg.screen().text

    await tg.send(MASTER, "  Тестовая   услуга ")
    assert any(isinstance(c, DeleteMessage) for c in tg.calls[-3:])  # ответ специалиста удалён
    assert "шаг 2 из 4" in tg.screen().text

    await tg.send(MASTER, "abc")
    assert "⚠️" in tg.screen().text and "шаг 2 из 4" in tg.screen().text

    await tg.press(MASTER, ServiceCb(action="dur", id=90).pack())
    await tg.send(MASTER, "1 500 ₽")
    await tg.press(MASTER, ServiceCb(action="skip").pack())
    assert "Услуга добавлена" in tg.screen().text and "1 ч 30 мин" in tg.screen().text

    new = (await db.list_services())[-1]
    assert (new["title"], new["duration_min"], new["price"], new["description"]) == ("Тестовая услуга", 90, 1500, None)


async def test_edit_price_with_error(tg):
    await tg.press(MASTER, ServiceCb(action="edit", id=1, field="price").pack())
    await tg.send(MASTER, "дорого")
    assert "⚠️" in tg.screen().text
    await tg.send(MASTER, "2000")
    assert "Сохранено" in tg.screen().text
    assert (await db.get_service(1))["price"] == 2000


async def test_start_command_is_not_taken_as_title(tg):
    await tg.press(MASTER, ServiceCb(action="edit", id=1, field="title").pack())
    await tg.send(MASTER, "/start")
    assert (await db.get_service(1))["title"] == "Экспресс"


async def test_hide_and_move(tg):
    await tg.press(MASTER, ServiceCb(action="toggle", id=4).pack())
    assert "Скрыта" in tg.screen().text
    assert len(await db.list_services(only_active=True)) == 3
    await tg.press(MASTER, ServiceCb(action="up", id=4).pack())
    assert "3 из 4" in tg.screen().text


async def test_cancel_returns_to_list(tg):
    await tg.press(MASTER, ServiceCb(action="add").pack())
    await tg.press(MASTER, ServiceCb(action="cancel").pack())
    assert "Нажмите на услугу" in tg.screen().text


async def test_delete_service_without_bookings(tg):
    await tg.press(MASTER, ServiceCb(action="delete", id=1).pack())
    assert "Удалить услугу «Экспресс»" in tg.screen().text and "записаны" not in tg.screen().text
    await tg.press(MASTER, ServiceCb(action="delete_ok", id=1).pack())
    assert "удалена" in tg.screen().text
    async with db.connect() as conn:
        row = await (await conn.execute("SELECT 1 FROM services WHERE id = 1")).fetchone()
    assert row is None  # записей не было — строка удалена совсем


async def test_delete_service_with_bookings_keeps_them(tg):
    await fill_schedule()
    await db.save_client(ANNA.id, None, name="Анна", phone="+7 900 123-45-67")
    booking_id = await book(ANNA.id, 2, next_monday().replace(hour=10))

    await tg.press(MASTER, ServiceCb(action="delete", id=2).pack())
    assert "уже записаны клиенты: 1" in tg.screen().text
    await tg.press(MASTER, ServiceCb(action="delete_ok", id=2).pack())

    assert 2 not in [s["id"] for s in await db.list_services()]       # нет у специалиста
    assert await db.get_service(2) is None                              # и для клиентов
    assert (await db.get_booking_details(booking_id))["status"] == "active"  # запись в силе
    assert (await db.get_active_booking(ANNA.id))["service_title"] == "Стандарт"

    # старая кнопка «Показать клиентам» не «воскрешает» удалённую услугу
    await tg.press(MASTER, ServiceCb(action="toggle", id=2).pack())
    assert await db.get_service(2) is None
    await tg.press(BORIS, BookCb(action="days", id=2).pack())
    assert "недоступна" in tg.screen().text


async def test_migration_adds_is_deleted_column(tmp_path):
    import config
    config.settings.db_path = str(tmp_path / "old.db")
    async with db.connect() as conn:  # база от старой версии бота — без колонки is_deleted
        await conn.execute(
            "CREATE TABLE services (id INTEGER PRIMARY KEY, master_id INTEGER NOT NULL, title TEXT NOT NULL,"
            " duration_min INTEGER NOT NULL, price INTEGER NOT NULL, description TEXT,"
            " is_active INTEGER NOT NULL DEFAULT 1, sort_order INTEGER NOT NULL DEFAULT 0)"
        )
        await conn.commit()
    await db.init_db()
    # колонка добавилась, запросы с is_deleted работают (4 — демо-услуги, созданные при первом запуске)
    assert len(await db.list_services()) == 4


async def test_stranger_cannot_open_master_section(tg):
    await tg.press(BORIS, ServiceCb(action="list").pack())
    answers = [c for c in tg.calls if isinstance(c, AnswerCallbackQuery)]
    assert "устарела" in answers[-1].text
