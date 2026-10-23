"""Напоминания клиентам: за 24 часа и за 1 час до визита.

Пока бот работает, рядом с ним крутится фоновая задача: раз в минуту она смотрит,
кому пора напомнить. Отметки «напомнили» хранятся в базе (reminded_24h, reminded_1h),
поэтому после перезапуска бота напоминания не повторяются.

Правила:
- записался меньше чем за сутки до визита — суточного напоминания нет;
- меньше чем за час — нет ни одного;
- если бот был выключен и суточное напоминание «проспал» до последнего часа,
  отправится только часовое.
"""
import asyncio
import html
import logging
from datetime import datetime, timedelta

from aiogram import Bot

import db
import formatting as fmt
import notifications
import texts
from config import DB_DATETIME_FORMAT, now
from keyboards import client as kb

log = logging.getLogger(__name__)

CHECK_EVERY_SECONDS = 60
DAY = timedelta(hours=24)
HOUR = timedelta(hours=1)


def parse(value: str) -> datetime:
    return datetime.strptime(value, DB_DATETIME_FORMAT)


def relative_day(start: datetime, current: datetime) -> str:
    """'Сегодня' / 'Завтра' / просто дата — для текста напоминания."""
    if start.date() == current.date():
        return texts.TODAY
    if start.date() == current.date() + timedelta(days=1):
        return texts.TOMORROW
    return fmt.day_full(start.date())


async def check(bot: Bot, current: datetime | None = None) -> None:
    """Одна проверка: отправить все напоминания, которым пора. current — «сейчас» (для тестов)."""
    current = current or now()
    current_str = current.strftime(DB_DATETIME_FORMAT)

    # --- за сутки
    until = (current + DAY).strftime(DB_DATETIME_FORMAT)
    for booking in await db.due_reminders("reminded_24h", current_str, until):
        if not await db.mark_reminded(booking["id"], "reminded_24h"):
            continue
        start, created = parse(booking["start_at"]), parse(booking["created_at"])
        if start - created < DAY:
            continue  # записался меньше чем за сутки — суточное напоминание не нужно
        if start - current <= HOUR:
            continue  # бот «проспал» суточное, скоро уйдёт часовое
        text = texts.REMIND_24H.format(
            service=html.escape(booking["service_title"]),
            when=relative_day(start, current),
            day=fmt.day_short(start.date()),
            start=f"{start:%H:%M}",
            tz=fmt.timezone(),
        )
        await notifications.send(bot, booking["client_tg_id"], text, kb.reminder_24h(booking["id"]))
        log.info("Напоминание за сутки: запись #%s", booking["id"])

    # --- за час
    until = (current + HOUR).strftime(DB_DATETIME_FORMAT)
    for booking in await db.due_reminders("reminded_1h", current_str, until):
        if not await db.mark_reminded(booking["id"], "reminded_1h"):
            continue
        start, created = parse(booking["start_at"]), parse(booking["created_at"])
        if start - created < HOUR:
            continue  # записался меньше чем за час — и так помнит
        text = texts.REMIND_1H.format(
            service=html.escape(booking["service_title"]),
            start=f"{start:%H:%M}",
            tz=fmt.timezone(),
        )
        await notifications.send(bot, booking["client_tg_id"], text, kb.reminder_1h())
        log.info("Напоминание за час: запись #%s", booking["id"])


async def run(bot: Bot) -> None:
    """Бесконечный цикл проверок. Ошибка в одной проверке не останавливает следующие."""
    log.info("Напоминания запущены")
    while True:
        try:
            await check(bot)
        except Exception:
            log.exception("Ошибка при отправке напоминаний")
        await asyncio.sleep(CHECK_EVERY_SECONDS)
