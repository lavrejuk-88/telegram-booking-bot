"""Раздел «📒 Записи» в меню специалиста: списки записей и отмена записи с причиной."""
import html
from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import db
import formatting as fmt
import notifications
import texts
from config import DB_DATETIME_FORMAT, now, settings
from handlers.common import edit_or_send, try_delete
from keyboards import master as kb
from keyboards.master import MasterBookingCb
from states import MasterCancel

router = Router()

LIST_LIMIT = 30   # больше записей в одном сообщении читать неудобно
REASON_MAX = 200


def period(code: str) -> tuple[str, str]:
    """Отрезок времени [начало, конец) для фильтра списка."""
    today = datetime.combine(now().date(), datetime.min.time())
    if code == "tomorrow":
        first, last = today + timedelta(days=1), today + timedelta(days=2)
    elif code == "week":
        first, last = today, today + timedelta(days=7)
    elif code == "all":
        first, last = now(), today + timedelta(days=settings.booking_horizon_days + 1)
    else:  # today: весь сегодняшний день, включая уже прошедшие визиты
        first, last = today, today + timedelta(days=1)
    return first.strftime(DB_DATETIME_FORMAT), last.strftime(DB_DATETIME_FORMAT)


async def show_list(bot: Bot, chat_id: int, message_id: int | None, code: str, note: str = "") -> None:
    bookings = await db.list_bookings(*period(code))
    shown = bookings[:LIST_LIMIT]

    lines = [texts.BOOKINGS_TITLE.format(title=texts.FILTER_TITLES.get(code, ""))]
    labels = []
    current_day = None
    for booking in shown:
        start = notifications.parse(booking["start_at"])
        end = notifications.parse(booking["end_at"])
        if start.date() != current_day:  # заголовок перед каждым новым днём
            current_day = start.date()
            lines.append(texts.BOOKINGS_DAY_HEADER.format(day=fmt.day_full(current_day)))
        lines.append(texts.BOOKINGS_LINE.format(
            start=f"{start:%H:%M}", end=f"{end:%H:%M}",
            service=html.escape(booking["service_title"]),
            name=html.escape(booking["client_name"]),
        ))
        labels.append(texts.BOOKING_BUTTON.format(
            day=fmt.day_short(start.date()), start=f"{start:%H:%M}", name=booking["client_name"]
        ))
    if not shown:
        lines.append("\n" + texts.BOOKINGS_EMPTY)
    else:
        lines.append(texts.BOOKINGS_HINT)
    if len(bookings) > LIST_LIMIT:
        lines.append(texts.BOOKINGS_LIMIT.format(limit=LIST_LIMIT))

    text = "\n".join(lines)
    if note:
        text = f"{note}\n\n{text}"
    await edit_or_send(bot, chat_id, message_id, text, kb.bookings_list(shown, code, labels))


@router.callback_query(F.data == "m:bookings")
@router.callback_query(MasterBookingCb.filter(F.action == "list"))
async def open_list(callback: CallbackQuery, state: FSMContext, bot: Bot,
                    callback_data: MasterBookingCb | None = None) -> None:
    await state.clear()
    code = callback_data.f if callback_data else "today"
    await show_list(bot, callback.message.chat.id, callback.message.message_id, code)
    await callback.answer()


async def active_booking_or_list(callback: CallbackQuery, data: MasterBookingCb, bot: Bot):
    booking = await db.get_booking_details(data.id)
    if booking is None or booking["status"] != "active":
        await callback.answer(texts.MASTER_CANCEL_GONE, show_alert=True)
        await show_list(bot, callback.message.chat.id, callback.message.message_id, data.f)
        return None
    return booking


@router.callback_query(MasterBookingCb.filter(F.action == "open"))
async def open_booking(callback: CallbackQuery, callback_data: MasterBookingCb, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    booking = await active_booking_or_list(callback, callback_data, bot)
    if booking is None:
        return
    text = texts.BOOKING_CARD.format(summary=notifications.summary(booking))
    markup = kb.booking_card(booking, callback_data.f)
    await edit_or_send(bot, callback.message.chat.id, callback.message.message_id, text, markup)
    await callback.answer()


# --- Отмена записи специалистом ---


async def ask_reason(bot: Bot, chat_id: int, state: FSMContext, booking, error: str = "") -> None:
    data = await state.get_data()
    text = texts.ASK_CANCEL_REASON.format(summary=notifications.summary(booking))
    if error:
        text += f"\n\n⚠️ {error}"
    await edit_or_send(bot, chat_id, data["prompt_id"], text, kb.cancel_reason(booking["id"], data["f"]))


async def finish_cancel(bot: Bot, chat_id: int, state: FSMContext, reason: str | None) -> None:
    data = await state.get_data()
    await state.clear()
    booking = await db.get_booking_details(data["booking_id"])
    if not await db.cancel_booking(booking["id"], by="master", reason=reason):
        await show_list(bot, chat_id, data["prompt_id"], data["f"], note=texts.MASTER_CANCEL_GONE)
        return
    await show_list(bot, chat_id, data["prompt_id"], data["f"], note=texts.MASTER_CANCELLED)
    await notifications.notify_client_cancelled(bot, booking, reason)


@router.callback_query(MasterBookingCb.filter(F.action == "cancel"))
async def start_cancel(callback: CallbackQuery, callback_data: MasterBookingCb, state: FSMContext, bot: Bot) -> None:
    booking = await active_booking_or_list(callback, callback_data, bot)
    if booking is None:
        return
    await state.set_state(MasterCancel.reason)
    await state.set_data({"booking_id": booking["id"], "prompt_id": callback.message.message_id, "f": callback_data.f})
    await ask_reason(bot, callback.message.chat.id, state, booking)
    await callback.answer()


@router.message(StateFilter(MasterCancel.reason), F.text)
async def reason_entered(message: Message, state: FSMContext, bot: Bot) -> None:
    await try_delete(message)
    reason = " ".join(message.text.split())
    if len(reason) > REASON_MAX:
        booking = await db.get_booking_details((await state.get_data())["booking_id"])
        await ask_reason(bot, message.chat.id, state, booking, error=texts.ERR_REASON.format(max=REASON_MAX))
        return
    await finish_cancel(bot, message.chat.id, state, reason or None)


@router.message(StateFilter(MasterCancel.reason))
async def reason_not_text(message: Message, state: FSMContext, bot: Bot) -> None:
    await try_delete(message)
    booking = await db.get_booking_details((await state.get_data())["booking_id"])
    await ask_reason(bot, message.chat.id, state, booking, error=texts.ERR_NEED_TEXT)


@router.callback_query(StateFilter(MasterCancel.reason), MasterBookingCb.filter(F.action == "nocause"))
async def cancel_without_reason(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    await finish_cancel(bot, callback.message.chat.id, state, None)
