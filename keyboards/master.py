from datetime import date

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import formatting as fmt
import texts
from logic.schedule import GRID_HOURS


def main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_M_BOOKINGS, callback_data="m:bookings")
    kb.button(text=texts.BTN_M_SCHEDULE, callback_data="m:schedule")
    kb.button(text=texts.BTN_M_SERVICES, callback_data="m:services")
    kb.button(text=texts.BTN_M_SETTINGS, callback_data="m:settings")
    kb.button(text=texts.BTN_M_CLIENT_VIEW, callback_data="m:client_view")
    kb.adjust(2, 2, 1)  # два ряда по две кнопки, затем одна
    return kb.as_markup()


# --- Услуги ---


class ServiceCb(CallbackData, prefix="svc"):
    """Данные кнопок раздела «Услуги».

    aiogram сам упакует их в строку вида 'svc:edit:3:price'
    и распакует обратно, когда кнопку нажмут.
    """
    action: str      # list, open, add, edit, toggle, up, down, dur, skip, cancel
    id: int = 0      # id услуги (для action=dur — количество минут)
    field: str = ""  # какое поле меняем (для action=edit)


DURATION_PRESETS = (30, 60, 90, 120)


def services_list(services: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in services:
        mark = "" if s["is_active"] else "🙈 "
        kb.button(
            text=f"{mark}{s['title']} · {fmt.duration(s['duration_min'])} · {fmt.price(s['price'])}",
            callback_data=ServiceCb(action="open", id=s["id"]),
        )
    kb.button(text=texts.BTN_ADD_SERVICE, callback_data=ServiceCb(action="add"))
    kb.button(text=texts.BTN_BACK, callback_data="m:menu")
    kb.adjust(1)
    return kb.as_markup()


def service_card(service) -> InlineKeyboardMarkup:
    sid = service["id"]
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_EDIT_TITLE, callback_data=ServiceCb(action="edit", id=sid, field="title"))
    kb.button(text=texts.BTN_EDIT_DURATION, callback_data=ServiceCb(action="edit", id=sid, field="duration_min"))
    kb.button(text=texts.BTN_EDIT_PRICE, callback_data=ServiceCb(action="edit", id=sid, field="price"))
    kb.button(text=texts.BTN_EDIT_DESCRIPTION, callback_data=ServiceCb(action="edit", id=sid, field="description"))
    kb.button(
        text=texts.BTN_HIDE if service["is_active"] else texts.BTN_SHOW,
        callback_data=ServiceCb(action="toggle", id=sid),
    )
    kb.button(text=texts.BTN_UP, callback_data=ServiceCb(action="up", id=sid))
    kb.button(text=texts.BTN_DOWN, callback_data=ServiceCb(action="down", id=sid))
    kb.button(text=texts.BTN_TO_LIST, callback_data=ServiceCb(action="list"))
    kb.adjust(2, 2, 1, 2, 1)
    return kb.as_markup()


def service_form(field: str, adding: bool) -> InlineKeyboardMarkup:
    """Кнопки под вопросом при добавлении или изменении услуги."""
    kb = InlineKeyboardBuilder()
    rows = []
    if field == "duration_min":
        for minutes in DURATION_PRESETS:
            kb.button(text=fmt.duration(minutes), callback_data=ServiceCb(action="dur", id=minutes))
        rows.append(len(DURATION_PRESETS))
    if field == "description":
        kb.button(
            text=texts.BTN_SKIP if adding else texts.BTN_CLEAR_DESCRIPTION,
            callback_data=ServiceCb(action="skip"),
        )
        rows.append(1)
    kb.button(text=texts.BTN_CANCEL, callback_data=ServiceCb(action="cancel"))
    rows.append(1)
    kb.adjust(*rows)
    return kb.as_markup()


# --- Расписание ---


class SchedCb(CallbackData, prefix="sch"):
    """Данные кнопок раздела «Расписание»."""
    action: str    # week, day, tpl, tpl_day, hour, save, off, cancel, ask, do
    day: str = ""  # дата '2026-11-05' (для недели — её понедельник)
    n: int = 0     # номер дня недели (tpl_day) или час (hour)
    op: str = ""   # что сделать с неделей: apply, copy, clear


def week_view(
    monday: date, days: list[date], days_off: set[date], can_prev: bool, can_next: bool
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for day in days:
        mark = texts.DAY_BUTTON_OFF_MARK if day in days_off else ""
        # Коротко «Пн 26»: по 4 кнопки в ряд длинный текст не влезет на экран телефона
        label = f"{fmt.WEEKDAYS_SHORT[day.weekday()]} {day.day}{mark}"
        kb.button(text=label, callback_data=SchedCb(action="day", day=day.isoformat()))
    rows = [4, 3]

    nav = 0
    if can_prev:
        kb.button(text=texts.BTN_PREV_WEEK, callback_data=SchedCb(action="week", day=monday.isoformat(), n=-1))
        nav += 1
    if can_next:
        kb.button(text=texts.BTN_NEXT_WEEK, callback_data=SchedCb(action="week", day=monday.isoformat(), n=1))
        nav += 1
    if nav:
        rows.append(nav)
    if can_prev:  # можно листать назад — значит, мы не на текущей неделе
        kb.button(text=texts.BTN_THIS_WEEK, callback_data=SchedCb(action="week"))
        rows.append(1)

    actions = [(texts.BTN_APPLY_TEMPLATE_WEEK, "apply")]
    if can_next:  # копировать на следующую неделю, только если до неё можно дойти
        actions.append((texts.BTN_COPY_WEEK, "copy"))
    actions.append((texts.BTN_CLEAR_WEEK, "clear"))
    for text, op in actions:
        kb.button(text=text, callback_data=SchedCb(action="ask", day=monday.isoformat(), op=op))
    kb.button(text=texts.BTN_TEMPLATE, callback_data=SchedCb(action="tpl"))
    kb.button(text=texts.BTN_BACK, callback_data="m:menu")
    rows += [1] * (len(actions) + 2)
    kb.adjust(*rows)
    return kb.as_markup()


def template_view() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for weekday, name in enumerate(fmt.WEEKDAYS_SHORT):
        kb.button(text=name, callback_data=SchedCb(action="tpl_day", n=weekday))
    kb.button(text=texts.BTN_TO_WEEK, callback_data=SchedCb(action="week"))
    kb.adjust(7, 1)
    return kb.as_markup()


def day_editor(hours: set[int]) -> InlineKeyboardMarkup:
    """Сетка часов-переключателей: ✅ — рабочий час."""
    kb = InlineKeyboardBuilder()
    for hour in GRID_HOURS:
        mark = "✅ " if hour in hours else ""
        # «10–11» понятнее, чем «10:00»: сразу видно, что кнопка — это целый час
        kb.button(text=f"{mark}{hour}–{hour + 1}", callback_data=SchedCb(action="hour", n=hour))
    kb.button(text=texts.BTN_SAVE, callback_data=SchedCb(action="save"))
    kb.button(text=texts.BTN_DAY_OFF, callback_data=SchedCb(action="off"))
    kb.button(text=texts.BTN_DISCARD, callback_data=SchedCb(action="cancel"))
    kb.adjust(*[3] * (len(GRID_HOURS) // 3), 1, 1, 1)
    return kb.as_markup()


def confirm(op: str, monday: date) -> InlineKeyboardMarkup:
    day = monday.isoformat()
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_YES, callback_data=SchedCb(action="do", day=day, op=op))
    kb.button(text=texts.BTN_NO, callback_data=SchedCb(action="week", day=day))
    kb.adjust(2)
    return kb.as_markup()


def schedule_conflict() -> InlineKeyboardMarkup:
    """Что делать, если новое расписание задевает записи клиентов."""
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_CONFLICT_KEEP, callback_data=SchedCb(action="conf", op="keep"))
    kb.button(text=texts.BTN_CONFLICT_CANCEL, callback_data=SchedCb(action="conf", op="cancel"))
    kb.button(text=texts.BTN_CONFLICT_ABORT, callback_data=SchedCb(action="conf", op="abort"))
    kb.adjust(1)
    return kb.as_markup()


# --- Записи ---


class MasterBookingCb(CallbackData, prefix="mb"):
    action: str    # list, open, cancel, nocause
    id: int = 0    # id записи
    f: str = "today"  # фильтр списка: today, tomorrow, week, all


BOOKING_FILTERS = [("today", texts.BTN_F_TODAY), ("tomorrow", texts.BTN_F_TOMORROW),
                   ("week", texts.BTN_F_WEEK), ("all", texts.BTN_F_ALL)]


def bookings_list(bookings: list, current: str, labels: list[str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for code, text in BOOKING_FILTERS:
        mark = "• " if code == current else ""
        kb.button(text=f"{mark}{text}", callback_data=MasterBookingCb(action="list", f=code))
    for booking, label in zip(bookings, labels):
        kb.button(text=label, callback_data=MasterBookingCb(action="open", id=booking["id"], f=current))
    kb.button(text=texts.BTN_BACK, callback_data="m:menu")
    kb.adjust(4, *[1] * len(bookings), 1)
    return kb.as_markup()


def booking_card(booking, current: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_M_CANCEL_BOOKING, callback_data=MasterBookingCb(action="cancel", id=booking["id"], f=current))
    if booking["client_username"]:
        kb.button(text=texts.BTN_WRITE_CLIENT, url=f"https://t.me/{booking['client_username']}")
    kb.button(text=texts.BTN_TO_BOOKINGS, callback_data=MasterBookingCb(action="list", f=current))
    kb.adjust(1)
    return kb.as_markup()


def cancel_reason(booking_id: int, current: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_NO_REASON, callback_data=MasterBookingCb(action="nocause", id=booking_id, f=current))
    kb.button(text=texts.BTN_DONT_CANCEL, callback_data=MasterBookingCb(action="open", id=booking_id, f=current))
    kb.adjust(1)
    return kb.as_markup()
