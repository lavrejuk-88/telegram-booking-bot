"""Уведомления: специалисту — о новых, отменённых и перенесённых записях; клиенту — об отмене мастером."""
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
from keyboards import client as client_kb

log = logging.getLogger(__name__)


def parse(value: str) -> datetime:
    return datetime.strptime(value, DB_DATETIME_FORMAT)


def when(start: datetime) -> str:
    """'Чт, 05.11.2026, 14:00'"""
    return f"{fmt.day_full(start.date())}, {start:%H:%M}"


def client_link(booking) -> str:
    """Имя клиента-ссылкой на его профиль и @username, если он есть: 'Анна · @anna_tg'."""
    name = html.escape(booking["client_name"])
    text = f'<a href="tg://user?id={booking["client_tg_id"]}">{name}</a>'
    if booking["client_username"]:
        text += f" · @{booking['client_username']}"
    return text


def booking_fields(booking) -> dict:
    """Всё о записи, уже готовое для подстановки в тексты."""
    start, end = parse(booking["start_at"]), parse(booking["end_at"])
    return {
        "client": client_link(booking),
        "phone": booking["client_phone"],
        "service": html.escape(booking["service_title"]),
        # Длительность — по самой записи: если услугу потом изменили, запись остаётся прежней
        "duration": fmt.duration(int((end - start).total_seconds() // 60)),
        "price": fmt.price(booking["price"]),
        "day": fmt.day_full(start.date()),
        "start": f"{start:%H:%M}",
        "end": f"{end:%H:%M}",
    }


def summary(booking) -> str:
    """Короткое описание записи: клиент, телефон, услуга, время."""
    return texts.BOOKING_SUMMARY.format(**booking_fields(booking))


def client_buttons(booking) -> InlineKeyboardMarkup | None:
    # Кнопку даём только при наличии username: ссылка вида t.me/username открывается всегда.
    # Ссылка по id в кнопке может не сработать из-за настроек приватности клиента,
    # и тогда Telegram не отправит всё уведомление целиком.
    if not booking["client_username"]:
        return None
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_WRITE_CLIENT, url=f"https://t.me/{booking['client_username']}")
    return kb.as_markup()


# --- Специалисту ---


async def notify_new_booking(bot: Bot, booking_id: int) -> None:
    booking = await db.get_booking_details(booking_id)
    text = texts.NOTIFY_NEW_BOOKING.format(**booking_fields(booking))
    await send(bot, settings.master_tg_id, text, client_buttons(booking))


async def notify_cancelled_by_client(bot: Bot, booking_id: int) -> None:
    booking = await db.get_booking_details(booking_id)
    text = texts.NOTIFY_CANCELLED.format(summary=summary(booking))
    await send(bot, settings.master_tg_id, text, client_buttons(booking))


async def notify_rescheduled(bot: Bot, old_id: int, new_id: int) -> None:
    old = await db.get_booking_details(old_id)
    new = await db.get_booking_details(new_id)
    fields = booking_fields(new)
    text = texts.NOTIFY_RESCHEDULED.format(
        **fields, old=when(parse(old["start_at"])), new=when(parse(new["start_at"]))
    )
    await send(bot, settings.master_tg_id, text, client_buttons(new))


# --- Клиенту ---


async def notify_client_cancelled(bot: Bot, booking, reason: str | None) -> None:
    """Мастер отменил запись — сообщаем клиенту и предлагаем записаться снова."""
    start = parse(booking["start_at"])
    text = texts.CLIENT_CANCELLED_BY_MASTER.format(
        service=html.escape(booking["service_title"]),
        day=fmt.day_full(start.date()),
        start=f"{start:%H:%M}",
        tz=fmt.timezone(),
    )
    if reason:
        text += texts.CLIENT_CANCEL_REASON.format(reason=html.escape(reason))
    text += texts.CLIENT_CANCEL_SORRY
    await send(bot, booking["client_tg_id"], text, client_kb.book_again())


async def send(bot: Bot, chat_id: int, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    """Отправляет сообщение и не падает, если не получилось.

    Например, человек заблокировал бота. Действие (запись, отмена) уже сохранено,
    а ошибка просто попадёт в журнал bot.log.
    """
    try:
        await bot.send_message(chat_id, text, reply_markup=markup)
    except TelegramAPIError:
        log.exception("Не удалось отправить сообщение в чат %s", chat_id)
