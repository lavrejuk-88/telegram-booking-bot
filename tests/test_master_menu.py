"""Меню специалиста: постоянная кнопка, «Как видит клиент», настройки приветствия."""
from aiogram.methods import DeleteMessage
from aiogram.types import ReplyKeyboardMarkup

import db
import texts
from conftest import ANNA, MASTER
from keyboards.master import ServiceCb


def callbacks(tg):
    return [b.callback_data for row in tg.screen().reply_markup.inline_keyboard for b in row]


async def test_start_sets_bottom_button_and_menu(tg):
    await tg.send(MASTER, "/start")
    intro, menu = tg.sent_to(111)[-2:]
    assert isinstance(intro.reply_markup, ReplyKeyboardMarkup)
    assert intro.reply_markup.keyboard[0][0].text == texts.BTN_MASTER_MENU
    assert menu.text == texts.MASTER_MENU


async def test_bottom_button_replaces_old_menu(tg):
    await tg.send(MASTER, "/start")
    before = len(tg.calls)
    await tg.send(MASTER, texts.BTN_MASTER_MENU)
    tail = tg.calls[before:]
    assert sum(isinstance(m, DeleteMessage) for m in tail) == 2  # нажатие и старое меню
    assert tg.sent_to(111)[-1].text == texts.MASTER_MENU


async def test_bottom_button_works_mid_dialog(tg):
    await tg.press(MASTER, ServiceCb(action="add").pack())
    await tg.send(MASTER, texts.BTN_MASTER_MENU)
    assert tg.sent_to(111)[-1].text == texts.MASTER_MENU
    assert all(s["title"] != texts.BTN_MASTER_MENU for s in await db.list_services())


async def test_client_cannot_use_master_button(tg):
    await tg.send(ANNA, texts.BTN_MASTER_MENU)
    assert tg.sent_to(ANNA.id)[-1].text == texts.UNKNOWN_MESSAGE


async def test_back_to_master_button_only_for_master(tg):
    await tg.press(MASTER, "m:client_view")
    assert "m:menu" in callbacks(tg)
    await tg.press(MASTER, "m:menu")
    assert texts.MASTER_MENU in tg.screen().text
    await tg.press(ANNA, "c:menu")
    assert "m:menu" not in callbacks(tg)
    await tg.press(ANNA, "m:menu")
    assert "устарела" in tg.alert()


async def test_welcome_edit_and_reset(tg):
    await tg.press(MASTER, "m:settings")
    assert "Здравствуйте" in tg.screen().text
    await tg.press(MASTER, "m:set_welcome")
    await tg.send(MASTER, "x" * 1001)
    assert "Слишком длинно" in tg.screen().text
    await tg.send(MASTER, "Привет! Я <Маша> & работаю\nна Ленина, 5")
    await tg.send(ANNA, "/start")
    assert tg.sent_to(ANNA.id)[-1].text == "Привет! Я &lt;Маша&gt; &amp; работаю\nна Ленина, 5"

    await tg.press(MASTER, "m:reset_welcome")
    assert (await db.get_master())["welcome_text"] == texts.DEFAULT_WELCOME
