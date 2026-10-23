from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import texts
from config import settings


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
