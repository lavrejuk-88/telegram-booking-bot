from datetime import date, datetime

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import formatting as fmt
import texts
from config import settings

DAYS_PER_PAGE = 9


def main_menu(has_booking: bool) -> InlineKeyboardMarkup:
    """Главное меню клиента. «Моя запись» есть, только если запись существует."""
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_BOOK, callback_data="c:book")
    if has_booking:
        kb.button(text=texts.BTN_MY_BOOKING, callback_data="c:my_booking")
    # Кнопка-ссылка: Telegram сам откроет чат со специалистом, бот в этом не участвует
    kb.button(text=texts.BTN_WRITE_MASTER, url=f"https://t.me/{settings.master_username}")
    kb.adjust(1)  # по одной кнопке в ряд
    return kb.as_markup()


# --- Запись ---


class BookCb(CallbackData, prefix="bk"):
    """Данные кнопок записи.

    Выбранная услуга, день и время хранятся прямо в кнопках, а не только в памяти бота.
    Поэтому путь записи не ломается, даже если бота перезапустили посреди выбора.
    """
    action: str     # days, day, time, name, phone, confirm
    id: int = 0     # id услуги
    day: str = ""   # '2026-11-05'
    n: int = 0      # номер страницы дней (days) или время в минутах от полуночи (time и дальше)


def _minutes(moment: datetime) -> int:
    # Время '14:30' в кнопке нельзя хранить как есть: ':' — разделитель в данных кнопки
    return moment.hour * 60 + moment.minute


def services(items: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in items:
        kb.button(
            text=f"{s['title']} · {fmt.duration(s['duration_min'])} · {fmt.price(s['price'])}",
            callback_data=BookCb(action="days", id=s["id"]),
        )
    kb.button(text=texts.BTN_BACK, callback_data="c:menu")
    kb.adjust(1)
    return kb.as_markup()


def no_services() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_WRITE_MASTER, url=f"https://t.me/{settings.master_username}")
    kb.button(text=texts.BTN_BACK, callback_data="c:menu")
    kb.adjust(1)
    return kb.as_markup()


def days(service_id: int, all_days: list[date], page: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    shown = all_days[page * DAYS_PER_PAGE:(page + 1) * DAYS_PER_PAGE]
    for day in shown:
        kb.button(text=fmt.day_short(day), callback_data=BookCb(action="day", id=service_id, day=day.isoformat()))
    rows = [3] * ((len(shown) + 2) // 3)

    nav = 0
    if page > 0:
        kb.button(text="◀️", callback_data=BookCb(action="days", id=service_id, n=page - 1))
        nav += 1
    kb.button(text=texts.BTN_BACK, callback_data="c:book")
    nav += 1
    if (page + 1) * DAYS_PER_PAGE < len(all_days):
        kb.button(text="▶️", callback_data=BookCb(action="days", id=service_id, n=page + 1))
        nav += 1
    rows.append(nav)
    kb.adjust(*rows)
    return kb.as_markup()


def no_days(service_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_WRITE_MASTER, url=f"https://t.me/{settings.master_username}")
    kb.button(text=texts.BTN_BACK, callback_data="c:book")
    kb.adjust(1)
    return kb.as_markup()


def times(service_id: int, day: date, starts: list[datetime], page: int) -> InlineKeyboardMarkup:
    """page — страница списка дней, чтобы «Назад» вернул на неё же."""
    kb = InlineKeyboardBuilder()
    for start in starts:
        kb.button(
            text=f"{start:%H:%M}",
            callback_data=BookCb(action="time", id=service_id, day=day.isoformat(), n=_minutes(start)),
        )
    kb.button(text=texts.BTN_BACK, callback_data=BookCb(action="days", id=service_id, n=page))
    kb.adjust(*[3] * ((len(starts) + 2) // 3), 1)
    return kb.as_markup()


def card(service_id: int, day: str, minutes: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_NAME, callback_data=BookCb(action="name", id=service_id, day=day, n=minutes))
    kb.button(text=texts.BTN_PHONE, callback_data=BookCb(action="phone", id=service_id, day=day, n=minutes))
    kb.button(text=texts.BTN_CONFIRM, callback_data=BookCb(action="confirm", id=service_id, day=day, n=minutes))
    kb.button(text=texts.BTN_BACK, callback_data=BookCb(action="day", id=service_id, day=day))
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def after_booking() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_MY_BOOKING, callback_data="c:my_booking")
    kb.button(text=texts.BTN_TO_MENU, callback_data="c:menu")
    kb.adjust(2)
    return kb.as_markup()


def share_contact() -> ReplyKeyboardMarkup:
    """Кнопка внизу экрана. Запросить контакт умеет только такая кнопка, а не кнопка под сообщением."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texts.BTN_SHARE_CONTACT, request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
