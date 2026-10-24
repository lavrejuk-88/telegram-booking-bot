"""Запись клиента: услуга → день → время → карточка (имя, телефон) → «Записаться».

Весь путь идёт в одном сообщении бота, которое меняется на месте.
Вопросы про имя и телефон приходят отдельным сообщением под карточкой;
после ответа и вопрос, и ответ удаляются, а данные появляются в карточке.

Что хранится в FSM, пока открыта карточка:
- slot     — выбранные услуга, день и время (их же дублируют кнопки карточки);
- card_id  — id сообщения-карточки, чтобы обновлять его после ввода имени/телефона;
- ask_id   — id сообщения с вопросом, чтобы потом его удалить;
- ask_field — о чём спросили: 'name' или 'phone'.
"""
import html
import logging
from datetime import date, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove, User

import db
import formatting as fmt
import notifications
import texts
from config import DB_DATETIME_FORMAT, settings
from handlers.common import edit_or_send, try_delete
from keyboards import client as kb
from keyboards import master as master_kb
from keyboards.client import DAYS_PER_PAGE, BookCb
from logic import availability, validation
from states import BookingForm

router = Router()
log = logging.getLogger(__name__)


def slot_start(day: str, minutes: int) -> datetime:
    return datetime.fromisoformat(day) + timedelta(minutes=minutes)


# --- Экраны ---


async def show_services(bot: Bot, chat_id: int, message_id: int | None, note: str = "") -> None:
    services = await db.list_services(only_active=True)
    if not services:
        await edit_or_send(bot, chat_id, message_id, texts.NO_SERVICES, kb.no_services())
        return
    text = texts.CHOOSE_SERVICE
    descriptions = [
        texts.SERVICE_DESCRIPTION_LINE.format(title=html.escape(s["title"]), description=html.escape(s["description"]))
        for s in services if s["description"]
    ]
    if descriptions:
        text += texts.CHOOSE_SERVICE_DESCRIPTIONS.format(lines="\n".join(descriptions))
    if note:
        text = f"{note}\n\n{text}"
    await edit_or_send(bot, chat_id, message_id, text, kb.services(services))


async def show_days(bot: Bot, chat_id: int, message_id: int | None, service, page: int, note: str = "") -> None:
    all_days = sorted(await availability.free_days(service["duration_min"]))
    title = html.escape(service["title"])
    duration = fmt.duration(service["duration_min"])
    if not all_days:
        await edit_or_send(
            bot, chat_id, message_id, texts.NO_DAYS.format(service=title, duration=duration), kb.no_days(service["id"])
        )
        return
    last_page = (len(all_days) - 1) // DAYS_PER_PAGE
    page = min(max(page, 0), last_page)
    text = texts.CHOOSE_DAY.format(service=title, duration=duration)
    if note:
        text = f"{note}\n\n{text}"
    await edit_or_send(bot, chat_id, message_id, text, kb.days(service["id"], all_days, page))


async def show_times(bot: Bot, chat_id: int, message_id: int | None, service, day: date, note: str = "") -> None:
    all_days = sorted(await availability.free_days(service["duration_min"]))
    if day not in all_days:
        # Пока клиент выбирал, на этот день разобрали всё время
        await show_days(bot, chat_id, message_id, service, page=0, note=texts.DAY_FULL)
        return
    starts = (await availability.free_times(service["duration_min"], day, day))[day]
    text = texts.CHOOSE_TIME.format(
        service=html.escape(service["title"]), day=fmt.day_full(day), tz=fmt.timezone()
    )
    if note:
        text = f"{note}\n\n{text}"
    page = all_days.index(day) // DAYS_PER_PAGE  # чтобы «Назад» вернул на ту же страницу дней
    await edit_or_send(bot, chat_id, message_id, text, kb.times(service["id"], day, starts, page))


async def show_card(bot: Bot, chat_id: int, message_id: int | None, service, start: datetime, user_id: int) -> None:
    client = await db.get_client(user_id)
    name = client["name"] if client and client["name"] else None
    phone = client["phone"] if client and client["phone"] else None
    end = start + timedelta(minutes=service["duration_min"])
    text = texts.CARD.format(
        service=html.escape(service["title"]),
        price=fmt.price(service["price"]),
        day=fmt.day_full(start.date()),
        start=f"{start:%H:%M}",
        end=f"{end:%H:%M}",
        tz=fmt.timezone(),
        name=html.escape(name) if name else texts.CARD_EMPTY,
        phone=phone or texts.CARD_EMPTY,
    )
    if not (name and phone):
        text += f"\n\n{texts.CARD_FILL_HINT}"
    minutes = start.hour * 60 + start.minute
    await edit_or_send(bot, chat_id, message_id, text, kb.card(service["id"], start.date().isoformat(), minutes))


async def show_already_booked(bot: Bot, chat_id: int, message_id: int | None, booking) -> None:
    start = datetime.strptime(booking["start_at"], DB_DATETIME_FORMAT)
    text = texts.ALREADY_BOOKED.format(
        service=html.escape(booking["service_title"]),
        day=fmt.day_full(start.date()),
        start=f"{start:%H:%M}",
        tz=fmt.timezone(),
    )
    await edit_or_send(bot, chat_id, message_id, text, kb.after_booking())


async def get_service_or_list(callback: CallbackQuery, bot: Bot, service_id: int):
    """Услуга для дальнейших шагов. Если её скрыли — показываем список заново."""
    service = await db.get_service(service_id)
    if service is None or not service["is_active"]:
        await show_services(bot, callback.message.chat.id, callback.message.message_id, note=texts.SERVICE_GONE)
        await callback.answer()
        return None
    return service


# --- Вопросы про имя и телефон ---


async def remove_reply_keyboard(bot: Bot, chat_id: int) -> None:
    """Убирает кнопку «Поделиться контактом» снизу экрана.

    Убрать такую кнопку можно только новым сообщением, поэтому отправляем его и сразу удаляем.
    Специалисту (если он проверяет запись «как клиент») вместо пустоты возвращаем его кнопку меню.
    """
    markup = master_kb.reply_menu() if chat_id == settings.master_tg_id else ReplyKeyboardRemove()
    message = await bot.send_message(chat_id, "✅", reply_markup=markup)
    await try_delete(message)


async def drop_question(bot: Bot, chat_id: int, state: FSMContext) -> None:
    """Удаляет висящий вопрос про имя или телефон (если он есть)."""
    data = await state.get_data()
    if data.get("ask_id"):
        try:
            await bot.delete_message(chat_id, data["ask_id"])
        except TelegramBadRequest:
            pass
        if data.get("ask_field") == "phone":
            await remove_reply_keyboard(bot, chat_id)
        await state.update_data(ask_id=None, ask_field=None)


async def ask(bot: Bot, chat_id: int, state: FSMContext, field: str, error: str = "") -> None:
    data = await state.get_data()
    question = texts.ASK_NAME if field == "name" else texts.ASK_PHONE
    if error:
        question += f"\n\n⚠️ {error}"

    # Повторяем тот же вопрос с подсказкой — правим старое сообщение, а не шлём новое
    if error and data.get("ask_id") and data.get("ask_field") == field:
        await edit_or_send(bot, chat_id, data["ask_id"], question, None)
    else:
        await drop_question(bot, chat_id, state)
        markup = kb.share_contact() if field == "phone" else None
        sent = await bot.send_message(chat_id, question, reply_markup=markup)
        await state.update_data(ask_id=sent.message_id, ask_field=field)
    await state.set_state(BookingForm.name if field == "name" else BookingForm.phone)


async def after_input(bot: Bot, chat_id: int, user: User, state: FSMContext) -> None:
    """Имя или телефон сохранены: убираем вопрос, обновляем карточку, спрашиваем недостающее."""
    await drop_question(bot, chat_id, state)
    data = await state.get_data()
    slot = data["slot"]
    service = await db.get_service(slot["id"])
    if service is None or not service["is_active"]:
        # Пока клиент вводил данные, специалист скрыл услугу. Данные клиента уже сохранены.
        await state.clear()
        await show_services(bot, chat_id, data["card_id"], note=texts.SERVICE_GONE)
        return
    await show_card(bot, chat_id, data["card_id"], service, slot_start(slot["day"], slot["n"]), user.id)

    client = await db.get_client(user.id)
    if not client["name"]:
        await ask(bot, chat_id, state, "name")
    elif not client["phone"]:
        await ask(bot, chat_id, state, "phone")
    else:
        await state.set_state(BookingForm.card)


async def remember_card(state: FSMContext, callback: CallbackQuery, data: BookCb) -> None:
    """Запоминаем открытую карточку в FSM (берём данные из кнопки — они там всегда есть)."""
    await state.update_data(
        slot={"id": data.id, "day": data.day, "n": data.n},
        card_id=callback.message.message_id,
    )


# --- Шаги записи ---


@router.callback_query(F.data == "c:book")
async def start_booking(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await drop_question(bot, callback.message.chat.id, state)
    await state.clear()
    booking = await db.get_active_booking(callback.from_user.id)
    if booking:
        await show_already_booked(bot, callback.message.chat.id, callback.message.message_id, booking)
    else:
        await show_services(bot, callback.message.chat.id, callback.message.message_id)
    await callback.answer()


@router.callback_query(BookCb.filter(F.action == "days"))
async def choose_day(callback: CallbackQuery, callback_data: BookCb, state: FSMContext, bot: Bot) -> None:
    await drop_question(bot, callback.message.chat.id, state)
    service = await get_service_or_list(callback, bot, callback_data.id)
    if service is None:
        return
    await show_days(bot, callback.message.chat.id, callback.message.message_id, service, callback_data.n)
    await callback.answer()


@router.callback_query(BookCb.filter(F.action == "day"))
async def choose_time(callback: CallbackQuery, callback_data: BookCb, state: FSMContext, bot: Bot) -> None:
    await drop_question(bot, callback.message.chat.id, state)
    await state.set_state(None)
    service = await get_service_or_list(callback, bot, callback_data.id)
    if service is None:
        return
    day = date.fromisoformat(callback_data.day)
    await show_times(bot, callback.message.chat.id, callback.message.message_id, service, day)
    await callback.answer()


@router.callback_query(BookCb.filter(F.action == "time"))
async def open_card(callback: CallbackQuery, callback_data: BookCb, state: FSMContext, bot: Bot) -> None:
    service = await get_service_or_list(callback, bot, callback_data.id)
    if service is None:
        return
    chat_id, message_id = callback.message.chat.id, callback.message.message_id
    day = date.fromisoformat(callback_data.day)
    start = slot_start(callback_data.day, callback_data.n)

    free = (await availability.free_times(service["duration_min"], day, day)).get(day, [])
    if start not in free:
        await callback.answer(texts.SLOT_TAKEN_ALERT, show_alert=True)
        await show_times(bot, chat_id, message_id, service, day)
        return

    await state.set_state(BookingForm.card)
    await remember_card(state, callback, callback_data)
    await show_card(bot, chat_id, message_id, service, start, callback.from_user.id)
    await callback.answer()

    # Новому клиенту сразу задаём вопросы по очереди
    client = await db.get_client(callback.from_user.id)
    if not client or not client["name"]:
        await ask(bot, chat_id, state, "name")
    elif not client["phone"]:
        await ask(bot, chat_id, state, "phone")


@router.callback_query(BookCb.filter(F.action.in_({"name", "phone"})))
async def edit_field(callback: CallbackQuery, callback_data: BookCb, state: FSMContext, bot: Bot) -> None:
    await remember_card(state, callback, callback_data)
    await ask(bot, callback.message.chat.id, state, callback_data.action)
    await callback.answer()


@router.message(BookingForm.name, F.text)
async def name_entered(message: Message, state: FSMContext, bot: Bot) -> None:
    await try_delete(message)
    try:
        name = validation.client_name(message.text)
    except validation.InvalidInput as error:
        await ask(bot, message.chat.id, state, "name", error=str(error))
        return
    await db.save_client(message.from_user.id, message.from_user.username, name=name)
    await after_input(bot, message.chat.id, message.from_user, state)


@router.message(BookingForm.phone, F.contact)
@router.message(BookingForm.phone, F.text)
async def phone_entered(message: Message, state: FSMContext, bot: Bot) -> None:
    await try_delete(message)
    if message.contact:
        # Кнопка «Поделиться контактом» отправляет свой контакт, но контакт можно и переслать чужой
        if message.contact.user_id != message.from_user.id:
            await ask(bot, message.chat.id, state, "phone", error=texts.ERR_FOREIGN_CONTACT)
            return
        raw = "+" + message.contact.phone_number.lstrip("+")
    else:
        raw = message.text
    try:
        phone = validation.phone(raw)
    except validation.InvalidInput as error:
        await ask(bot, message.chat.id, state, "phone", error=str(error))
        return
    await db.save_client(message.from_user.id, message.from_user.username, phone=phone)
    await after_input(bot, message.chat.id, message.from_user, state)


@router.message(BookingForm.name)
@router.message(BookingForm.phone)
async def wrong_input(message: Message, state: FSMContext, bot: Bot) -> None:
    """Прислали стикер, фото и т.п. вместо имени или телефона."""
    await try_delete(message)
    field = "name" if await state.get_state() == BookingForm.name.state else "phone"
    await ask(bot, message.chat.id, state, field, error=texts.ERR_NEED_TEXT)


@router.callback_query(BookCb.filter(F.action == "confirm"))
async def confirm(callback: CallbackQuery, callback_data: BookCb, state: FSMContext, bot: Bot) -> None:
    chat_id, message_id = callback.message.chat.id, callback.message.message_id
    user = callback.from_user
    await remember_card(state, callback, callback_data)

    client = await db.get_client(user.id)
    if not client or not client["name"] or not client["phone"]:
        await callback.answer(texts.NEED_NAME_PHONE, show_alert=True)
        await ask(bot, chat_id, state, "name" if not client or not client["name"] else "phone")
        return

    await drop_question(bot, chat_id, state)
    service = await get_service_or_list(callback, bot, callback_data.id)
    if service is None:
        return
    start = slot_start(callback_data.day, callback_data.n)
    try:
        booking_id = await db.create_booking(
            user.id, service["id"],
            start.strftime(DB_DATETIME_FORMAT),
            availability.horizon().strftime(DB_DATETIME_FORMAT),
        )
    except db.BookingError as error:
        await callback.answer()
        if error.code == "taken":
            await state.set_state(None)
            await show_times(bot, chat_id, message_id, service, start.date(), note=texts.SLOT_TAKEN)
        elif error.code == "has_booking":
            await state.clear()
            await show_already_booked(bot, chat_id, message_id, await db.get_active_booking(user.id))
        elif error.code == "service":
            await state.clear()
            await show_services(bot, chat_id, message_id, note=texts.SERVICE_GONE)
        else:  # 'client': данные клиента пропали — спросим заново
            await ask(bot, chat_id, state, "name")
        return

    await state.clear()
    text = texts.BOOKED.format(
        service=html.escape(service["title"]),
        day=fmt.day_full(start.date()),
        start=f"{start:%H:%M}",
        tz=fmt.timezone(),
    )
    await edit_or_send(bot, chat_id, message_id, text, kb.after_booking())
    await callback.answer()
    log.info("Новая запись #%s: клиент %s, %s", booking_id, user.id, start)
    # Сначала клиент видит «Вы записаны», потом уходит уведомление специалисту
    await notifications.notify_new_booking(bot, booking_id)
