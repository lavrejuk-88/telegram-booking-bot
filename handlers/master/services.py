"""Раздел «🧾 Услуги» в меню специалиста.

Как устроен диалог добавления/изменения:
- бот задаёт вопрос, меняя на месте своё сообщение (его id храним в FSM как prompt_id);
- специалист отвечает текстом; бот удаляет ответ, чтобы чат оставался чистым;
- если ответ неверный, в том же сообщении появляется подсказка, что не так.
"""
import html

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import db
import formatting as fmt
import texts
from handlers.common import edit_or_send, try_delete
from keyboards import master as kb
from keyboards.master import ServiceCb
from logic import validation
from states import ServiceForm

router = Router()

# Порядок вопросов при добавлении новой услуги
ADD_ORDER = ["title", "duration_min", "price", "description"]

FIELD_STATES = {
    "title": ServiceForm.title,
    "duration_min": ServiceForm.duration,
    "price": ServiceForm.price,
    "description": ServiceForm.description,
}

PARSERS = {
    "title": validation.service_title,
    "duration_min": validation.service_duration,
    "price": validation.service_price,
    "description": validation.service_description,
}


# --- Экраны: список и карточка ---


async def show_list(bot: Bot, chat_id: int, message_id: int | None) -> None:
    services = await db.list_services()
    text = texts.SERVICES_LIST if services else texts.SERVICES_EMPTY
    await edit_or_send(bot, chat_id, message_id, text, kb.services_list(services))


async def show_card(bot: Bot, chat_id: int, message_id: int | None, service_id: int, note: str = "") -> None:
    services = await db.list_services()
    ids = [s["id"] for s in services]
    if service_id not in ids:
        await show_list(bot, chat_id, message_id)
        return
    service = services[ids.index(service_id)]
    text = texts.SERVICE_CARD.format(
        # html.escape: если в названии есть '<' или '&', разметка не сломается
        title=html.escape(service["title"]),
        duration=fmt.duration(service["duration_min"]),
        price=fmt.price(service["price"]),
        description=html.escape(service["description"]) if service["description"] else texts.SERVICE_NO_DESCRIPTION,
        status=texts.SERVICE_VISIBLE if service["is_active"] else texts.SERVICE_HIDDEN,
        position=ids.index(service_id) + 1,
        total=len(ids),
    )
    if note:
        text = f"{note}\n\n{text}"
    await edit_or_send(bot, chat_id, message_id, text, kb.service_card(service))


@router.callback_query(F.data == "m:services")
@router.callback_query(ServiceCb.filter(F.action == "list"))
async def open_list(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await show_list(bot, callback.message.chat.id, callback.message.message_id)
    await callback.answer()


@router.callback_query(ServiceCb.filter(F.action == "open"))
async def open_card(callback: CallbackQuery, callback_data: ServiceCb, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await show_card(bot, callback.message.chat.id, callback.message.message_id, callback_data.id)
    await callback.answer()


@router.callback_query(ServiceCb.filter(F.action.in_({"toggle", "up", "down"})))
async def change_card(callback: CallbackQuery, callback_data: ServiceCb, bot: Bot) -> None:
    if await db.get_service(callback_data.id) is None:
        await callback.answer(texts.SERVICE_NOT_FOUND, show_alert=True)
        return
    if callback_data.action == "toggle":
        await db.toggle_service(callback_data.id)
    else:
        await db.move_service(callback_data.id, -1 if callback_data.action == "up" else 1)
    await show_card(bot, callback.message.chat.id, callback.message.message_id, callback_data.id)
    await callback.answer()


# --- Диалог: вопросы и ответы ---


async def ask(bot: Bot, chat_id: int, state: FSMContext, field: str, error: str = "") -> None:
    """Задаёт вопрос про поле field (или повторяет его с подсказкой об ошибке)."""
    await state.set_state(FIELD_STATES[field])
    data = await state.get_data()
    adding = data["mode"] == "add"

    if adding:
        header = texts.SERVICE_ADD_HEADER.format(step=ADD_ORDER.index(field) + 1, total=len(ADD_ORDER))
    else:
        header = texts.SERVICE_EDIT_HEADER.format(title=html.escape(data["title"]))
    text = f"{header}\n\n{texts.SERVICE_PROMPTS[field]}"
    if error:
        text += f"\n\n⚠️ {error}"

    prompt_id = await edit_or_send(bot, chat_id, data["prompt_id"], text, kb.service_form(field, adding))
    await state.update_data(field=field, prompt_id=prompt_id)


async def accept(bot: Bot, chat_id: int, state: FSMContext, value: str | int | None) -> None:
    """Принимает проверенный ответ и решает, что дальше."""
    data = await state.get_data()
    field = data["field"]

    if data["mode"] == "edit":
        await db.update_service(data["service_id"], field, value)
        await state.clear()
        await show_card(bot, chat_id, data["prompt_id"], data["service_id"], note=texts.SERVICE_SAVED)
        return

    # Добавление: копим ответы в FSM, пока не ответят на все вопросы
    new = {**data.get("new", {}), field: value}
    await state.update_data(new=new)
    step = ADD_ORDER.index(field)
    if step + 1 < len(ADD_ORDER):
        await ask(bot, chat_id, state, ADD_ORDER[step + 1])
        return

    service_id = await db.add_service(**new)
    await state.clear()
    await show_card(bot, chat_id, data["prompt_id"], service_id, note=texts.SERVICE_ADDED)


@router.callback_query(ServiceCb.filter(F.action == "add"))
async def start_add(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.set_data({"mode": "add", "prompt_id": callback.message.message_id, "new": {}})
    await ask(bot, callback.message.chat.id, state, ADD_ORDER[0])
    await callback.answer()


@router.callback_query(ServiceCb.filter(F.action == "edit"))
async def start_edit(callback: CallbackQuery, callback_data: ServiceCb, state: FSMContext, bot: Bot) -> None:
    service = await db.get_service(callback_data.id)
    if service is None or callback_data.field not in FIELD_STATES:
        await callback.answer(texts.SERVICE_NOT_FOUND, show_alert=True)
        return
    await state.set_data({
        "mode": "edit",
        "service_id": service["id"],
        "title": service["title"],
        "prompt_id": callback.message.message_id,
    })
    await ask(bot, callback.message.chat.id, state, callback_data.field)
    await callback.answer()


@router.message(StateFilter(ServiceForm), F.text)
async def text_answer(message: Message, state: FSMContext, bot: Bot) -> None:
    await try_delete(message)
    field = (await state.get_data())["field"]
    try:
        value = PARSERS[field](message.text)
    except validation.InvalidInput as error:
        await ask(bot, message.chat.id, state, field, error=str(error))
        return
    await accept(bot, message.chat.id, state, value)


@router.message(StateFilter(ServiceForm))
async def not_text_answer(message: Message, state: FSMContext, bot: Bot) -> None:
    """Прислали стикер, фото и т.п. вместо текста."""
    await try_delete(message)
    await ask(bot, message.chat.id, state, (await state.get_data())["field"], error=texts.ERR_NEED_TEXT)


@router.callback_query(ServiceForm.duration, ServiceCb.filter(F.action == "dur"))
async def duration_preset(callback: CallbackQuery, callback_data: ServiceCb, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    await accept(bot, callback.message.chat.id, state, callback_data.id)


@router.callback_query(ServiceForm.description, ServiceCb.filter(F.action == "skip"))
async def skip_description(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    await accept(bot, callback.message.chat.id, state, None)


@router.callback_query(ServiceCb.filter(F.action == "cancel"))
async def cancel(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    chat_id, message_id = callback.message.chat.id, callback.message.message_id
    if data.get("mode") == "edit":
        await show_card(bot, chat_id, message_id, data["service_id"])
    else:
        await show_list(bot, chat_id, message_id)
    await callback.answer()
