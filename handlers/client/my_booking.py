"""«Моя запись»: просмотр, отмена и перенос записи клиентом."""
import html
from datetime import date, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

import db
import formatting as fmt
import notifications
import texts
from config import DB_DATETIME_FORMAT
from handlers.common import edit_or_send
from keyboards import client as kb
from keyboards.client import DAYS_PER_PAGE, MyCb
from logic import availability

router = Router()


def parse(value: str) -> datetime:
    return datetime.strptime(value, DB_DATETIME_FORMAT)


def when(start: datetime) -> str:
    """'Чт, 05.11.2026, 14:00'"""
    return f"{fmt.day_full(start.date())}, {start:%H:%M}"


async def own_booking(callback: CallbackQuery, booking_id: int):
    """Запись клиента по id из кнопки. Если она уже неактивна — показываем «Моя запись» заново."""
    booking = await db.get_active_booking(callback.from_user.id)
    if booking is None or booking["id"] != booking_id:
        await callback.answer(texts.BOOKING_GONE, show_alert=True)
        await show_my_booking(callback)
        return None
    return booking


async def show_my_booking(callback: CallbackQuery) -> None:
    chat_id, message_id = callback.message.chat.id, callback.message.message_id
    booking = await db.get_active_booking(callback.from_user.id)
    if booking is None:
        await edit_or_send(callback.bot, chat_id, message_id, texts.NO_BOOKING, kb.no_booking())
        return
    start, end = parse(booking["start_at"]), parse(booking["end_at"])
    text = texts.MY_BOOKING.format(
        service=html.escape(booking["service_title"]),
        price=fmt.price(booking["price"]),
        day=fmt.day_full(start.date()),
        start=f"{start:%H:%M}",
        end=f"{end:%H:%M}",
        tz=fmt.timezone(),
    )
    await edit_or_send(callback.bot, chat_id, message_id, text, kb.my_booking(booking["id"]))


@router.callback_query(F.data == "c:my_booking")
async def open_my_booking(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show_my_booking(callback)
    await callback.answer()


# --- Отмена ---


@router.callback_query(MyCb.filter(F.action == "cancel"))
async def ask_cancel(callback: CallbackQuery, callback_data: MyCb, bot: Bot) -> None:
    booking = await own_booking(callback, callback_data.id)
    if booking is None:
        return
    start = parse(booking["start_at"])
    text = texts.CANCEL_CONFIRM.format(
        service=html.escape(booking["service_title"]),
        day=fmt.day_full(start.date()),
        start=f"{start:%H:%M}",
        tz=fmt.timezone(),
    )
    await edit_or_send(bot, callback.message.chat.id, callback.message.message_id, text, kb.cancel_confirm(booking["id"]))
    await callback.answer()


@router.callback_query(MyCb.filter(F.action == "cancel_ok"))
async def do_cancel(callback: CallbackQuery, callback_data: MyCb, bot: Bot) -> None:
    booking = await own_booking(callback, callback_data.id)
    if booking is None:
        return
    if not await db.cancel_booking(booking["id"], by="client"):
        await callback.answer(texts.BOOKING_GONE, show_alert=True)
        await show_my_booking(callback)
        return
    await edit_or_send(
        bot, callback.message.chat.id, callback.message.message_id, texts.CANCELLED_BY_CLIENT, kb.book_again()
    )
    await callback.answer()
    await notifications.notify_cancelled_by_client(bot, booking["id"])


# --- Перенос: день → время → подтверждение ---


async def show_reschedule_days(callback: CallbackQuery, booking, page: int) -> None:
    chat_id, message_id = callback.message.chat.id, callback.message.message_id
    minutes = availability.booking_minutes(booking)
    all_days = sorted(await availability.free_days(minutes, exclude_booking_id=booking["id"]))
    if not all_days:
        await edit_or_send(callback.bot, chat_id, message_id, texts.RESCHEDULE_NO_DAYS, kb.my_booking(booking["id"]))
        return
    page = min(max(page, 0), (len(all_days) - 1) // DAYS_PER_PAGE)
    text = texts.RESCHEDULE_DAY.format(
        service=html.escape(booking["service_title"]), current=when(parse(booking["start_at"]))
    )
    await edit_or_send(callback.bot, chat_id, message_id, text, kb.reschedule_days(booking["id"], all_days, page))


@router.callback_query(MyCb.filter(F.action == "rs_days"))
async def reschedule_choose_day(callback: CallbackQuery, callback_data: MyCb) -> None:
    booking = await own_booking(callback, callback_data.id)
    if booking is None:
        return
    await show_reschedule_days(callback, booking, callback_data.n)
    await callback.answer()


@router.callback_query(MyCb.filter(F.action == "rs_day"))
async def reschedule_choose_time(callback: CallbackQuery, callback_data: MyCb, bot: Bot) -> None:
    booking = await own_booking(callback, callback_data.id)
    if booking is None:
        return
    minutes = availability.booking_minutes(booking)
    day = date.fromisoformat(callback_data.day)
    all_days = sorted(await availability.free_days(minutes, exclude_booking_id=booking["id"]))
    if day not in all_days:
        await show_reschedule_days(callback, booking, 0)
        await callback.answer(texts.DAY_FULL, show_alert=True)
        return
    starts = (await availability.free_times(minutes, day, day, exclude_booking_id=booking["id"]))[day]
    current = parse(booking["start_at"])
    starts = [s for s in starts if s != current]  # своё же текущее время не предлагаем
    text = texts.RESCHEDULE_TIME.format(
        service=html.escape(booking["service_title"]), day=fmt.day_full(day), tz=fmt.timezone()
    )
    page = all_days.index(day) // DAYS_PER_PAGE
    markup = kb.reschedule_times(booking["id"], day, starts, page)
    await edit_or_send(bot, callback.message.chat.id, callback.message.message_id, text, markup)
    await callback.answer()


@router.callback_query(MyCb.filter(F.action == "rs_time"))
async def reschedule_confirm(callback: CallbackQuery, callback_data: MyCb, bot: Bot) -> None:
    booking = await own_booking(callback, callback_data.id)
    if booking is None:
        return
    new_start = datetime.fromisoformat(callback_data.day) + timedelta(minutes=callback_data.n)
    text = texts.RESCHEDULE_CONFIRM.format(
        service=html.escape(booking["service_title"]),
        old=when(parse(booking["start_at"])),
        new=when(new_start),
        tz=fmt.timezone(),
    )
    markup = kb.reschedule_confirm(booking["id"], callback_data.day, callback_data.n)
    await edit_or_send(bot, callback.message.chat.id, callback.message.message_id, text, markup)
    await callback.answer()


@router.callback_query(MyCb.filter(F.action == "rs_ok"))
async def do_reschedule(callback: CallbackQuery, callback_data: MyCb, bot: Bot) -> None:
    booking = await own_booking(callback, callback_data.id)
    if booking is None:
        return
    new_start = datetime.fromisoformat(callback_data.day) + timedelta(minutes=callback_data.n)
    try:
        new_id = await db.reschedule_booking(
            booking["id"], callback.from_user.id,
            new_start.strftime(DB_DATETIME_FORMAT),
            availability.horizon().strftime(DB_DATETIME_FORMAT),
        )
    except db.BookingError as error:
        if error.code == "gone":
            await callback.answer(texts.BOOKING_GONE, show_alert=True)
            await show_my_booking(callback)
        else:
            await callback.answer(texts.SLOT_TAKEN_ALERT, show_alert=True)
            await show_reschedule_days(callback, booking, 0)
        return

    text = texts.RESCHEDULED.format(
        service=html.escape(booking["service_title"]), new=when(new_start), tz=fmt.timezone()
    )
    await edit_or_send(bot, callback.message.chat.id, callback.message.message_id, text, kb.after_booking())
    await callback.answer()
    await notifications.notify_rescheduled(bot, booking["id"], new_id)
