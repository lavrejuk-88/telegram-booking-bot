from datetime import date, datetime

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import formatting as fmt
import texts
from config import settings

DAYS_PER_PAGE = 9


def main_menu(has_booking: bool, is_master: bool = False) -> InlineKeyboardMarkup:
    """Главное меню клиента. «Моя запись» есть, только если запись существует.

    is_master — меню открыл сам специалист («Как видит клиент»): добавляем кнопку возврата.
    Обычные клиенты её не видят, а если и пришлют такое нажатие, роутер специалиста его не пропустит.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_BOOK, callback_data="c:book")
    if has_booking:
        kb.button(text=texts.BTN_MY_BOOKING, callback_data="c:my_booking")
    # Кнопка-ссылка: Telegram сам откроет чат со специалистом, бот в этом не участвует
    kb.button(text=texts.BTN_WRITE_MASTER, url=f"https://t.me/{settings.master_username}")
    if is_master:
        kb.button(text=texts.BTN_BACK_TO_MASTER, callback_data="m:menu")
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


def _days(all_days: list[date], page: int, day_cb, page_cb, back_cb) -> InlineKeyboardMarkup:
    """Список дней по страницам. day_cb(день) и page_cb(страница) — что положить в кнопки.

    Один и тот же список дней нужен и для новой записи, и для переноса — отличаются только данные кнопок.
    """
    kb = InlineKeyboardBuilder()
    shown = all_days[page * DAYS_PER_PAGE:(page + 1) * DAYS_PER_PAGE]
    for day in shown:
        kb.button(text=fmt.day_short(day), callback_data=day_cb(day))
    rows = [3] * ((len(shown) + 2) // 3)

    nav = 0
    if page > 0:
        kb.button(text="◀️", callback_data=page_cb(page - 1))
        nav += 1
    kb.button(text=texts.BTN_BACK, callback_data=back_cb)
    nav += 1
    if (page + 1) * DAYS_PER_PAGE < len(all_days):
        kb.button(text="▶️", callback_data=page_cb(page + 1))
        nav += 1
    rows.append(nav)
    kb.adjust(*rows)
    return kb.as_markup()


def _times(starts: list[datetime], time_cb, back_cb) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for start in starts:
        kb.button(text=f"{start:%H:%M}", callback_data=time_cb(start))
    kb.button(text=texts.BTN_BACK, callback_data=back_cb)
    kb.adjust(*[3] * ((len(starts) + 2) // 3), 1)
    return kb.as_markup()


def days(service_id: int, all_days: list[date], page: int) -> InlineKeyboardMarkup:
    return _days(
        all_days, page,
        day_cb=lambda day: BookCb(action="day", id=service_id, day=day.isoformat()),
        page_cb=lambda p: BookCb(action="days", id=service_id, n=p),
        back_cb="c:book",
    )


def no_days(service_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_WRITE_MASTER, url=f"https://t.me/{settings.master_username}")
    kb.button(text=texts.BTN_BACK, callback_data="c:book")
    kb.adjust(1)
    return kb.as_markup()


def times(service_id: int, day: date, starts: list[datetime], page: int) -> InlineKeyboardMarkup:
    """page — страница списка дней, чтобы «Назад» вернул на неё же."""
    return _times(
        starts,
        time_cb=lambda start: BookCb(action="time", id=service_id, day=day.isoformat(), n=_minutes(start)),
        back_cb=BookCb(action="days", id=service_id, n=page),
    )


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


# --- Моя запись: отмена и перенос ---


class MyCb(CallbackData, prefix="my"):
    action: str     # cancel, cancel_ok, rs_days, rs_day, rs_time, rs_ok
    id: int = 0     # id записи
    day: str = ""
    n: int = 0      # страница дней (rs_days) или время в минутах (rs_time, rs_ok)


def my_booking(booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_RESCHEDULE, callback_data=MyCb(action="rs_days", id=booking_id))
    kb.button(text=texts.BTN_CANCEL_BOOKING, callback_data=MyCb(action="cancel", id=booking_id))
    kb.button(text=texts.BTN_TO_MENU, callback_data="c:menu")
    kb.adjust(2, 1)
    return kb.as_markup()


def no_booking() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_BOOK, callback_data="c:book")
    kb.button(text=texts.BTN_TO_MENU, callback_data="c:menu")
    kb.adjust(1)
    return kb.as_markup()


def cancel_confirm(booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_CANCEL_YES, callback_data=MyCb(action="cancel_ok", id=booking_id))
    kb.button(text=texts.BTN_CANCEL_NO, callback_data="c:my_booking")
    kb.adjust(1)
    return kb.as_markup()


def book_again() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_BOOK_AGAIN, callback_data="c:book")
    kb.button(text=texts.BTN_TO_MENU, callback_data="c:menu")
    kb.adjust(1)
    return kb.as_markup()


def reschedule_days(booking_id: int, all_days: list[date], page: int) -> InlineKeyboardMarkup:
    return _days(
        all_days, page,
        day_cb=lambda day: MyCb(action="rs_day", id=booking_id, day=day.isoformat()),
        page_cb=lambda p: MyCb(action="rs_days", id=booking_id, n=p),
        back_cb="c:my_booking",
    )


def reschedule_times(booking_id: int, day: date, starts: list[datetime], page: int) -> InlineKeyboardMarkup:
    return _times(
        starts,
        time_cb=lambda start: MyCb(action="rs_time", id=booking_id, day=day.isoformat(), n=_minutes(start)),
        back_cb=MyCb(action="rs_days", id=booking_id, n=page),
    )


def reschedule_confirm(booking_id: int, day: str, minutes: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_RESCHEDULE_YES, callback_data=MyCb(action="rs_ok", id=booking_id, day=day, n=minutes))
    kb.button(text=texts.BTN_BACK, callback_data=MyCb(action="rs_day", id=booking_id, day=day))
    kb.adjust(1)
    return kb.as_markup()


def share_contact() -> ReplyKeyboardMarkup:
    """Кнопка внизу экрана. Запросить контакт умеет только такая кнопка, а не кнопка под сообщением."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texts.BTN_SHARE_CONTACT, request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
