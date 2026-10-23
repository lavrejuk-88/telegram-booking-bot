from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

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
