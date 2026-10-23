"""Уведомления специалисту о событиях: новая запись (позже — отмена и перенос)."""
import html
import logging
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import db
import formatting as fmt
import texts
from config import DB_DATETIME_FORMAT, settings

log = logging.getLogger(__name__)


def client_link(booking) -> str:
    """Имя клиента-ссылкой на его профиль и @username, если он есть: 'Анна · @anna_tg'."""
    name = html.escape(booking["client_name"])
    text = f'<a href="tg://user?id={booking["client_tg_id"]}">{name}</a>'
    if booking["client_username"]:
        text += f" · @{booking['client_username']}"
    return text


def client_buttons(booking) -> InlineKeyboardMarkup | None:
    # Кнопку даём только при наличии username: ссылка вида t.me/username открывается всегда.
    # Ссылка по id в кнопке может не сработать из-за настроек приватности клиента,
    # и тогда Telegram не отправит всё уведомление целиком.
    if not booking["client_username"]:
        return None
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_WRITE_CLIENT, url=f"https://t.me/{booking['client_username']}")
    return kb.as_markup()


async def notify_new_booking(bot: Bot, booking_id: int) -> None:
    booking = await db.get_booking_details(booking_id)
    start = datetime.strptime(booking["start_at"], DB_DATETIME_FORMAT)
    end = datetime.strptime(booking["end_at"], DB_DATETIME_FORMAT)
    text = texts.NOTIFY_NEW_BOOKING.format(
        client=client_link(booking),
        phone=booking["client_phone"],
        service=html.escape(booking["service_title"]),
        duration=fmt.duration(booking["duration_min"]),
        price=fmt.price(booking["price"]),
        day=fmt.day_full(start.date()),
        start=f"{start:%H:%M}",
        end=f"{end:%H:%M}",
    )
    await send_to_master(bot, text, client_buttons(booking))


async def send_to_master(bot: Bot, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    """Отправляет сообщение специалисту.

    Если не получилось (специалист ни разу не открывал бота или заблокировал его),
    клиент об этом не узнает: запись уже сохранена, ошибка просто попадёт в журнал bot.log.
    """
    try:
        await bot.send_message(settings.master_tg_id, text, reply_markup=markup)
    except TelegramAPIError:
        log.exception("Не удалось отправить уведомление специалисту")
