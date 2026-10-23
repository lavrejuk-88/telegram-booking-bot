from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import formatting as fmt
import texts


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
