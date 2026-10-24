"""Раздел «Услуги» у специалиста."""
from aiogram.methods import AnswerCallbackQuery, DeleteMessage

import db
from conftest import BORIS, MASTER
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


async def test_stranger_cannot_open_master_section(tg):
    await tg.press(BORIS, ServiceCb(action="list").pack())
    answers = [c for c in tg.calls if isinstance(c, AnswerCallbackQuery)]
    assert "устарела" in answers[-1].text
