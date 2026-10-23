"""Хендлеры клиента: всё, что видит обычный пользователь."""
import html

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import db
import texts
from keyboards import client as kb

router = Router()


async def menu_content(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Текст и кнопки главного меню. Используется и специалистом («Как видит клиент»)."""
    master = await db.get_master()
    # escape: текст приветствия пишет специалист, и символы вроде '<' не должны ломать разметку
    welcome = html.escape(master["welcome_text"] or texts.DEFAULT_WELCOME)
    return welcome, kb.main_menu(has_booking=await db.has_active_booking(user_id))


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    # /start всегда возвращает в начало, даже из середины записи
    await state.clear()
    text, markup = await menu_content(message.from_user.id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.in_({"c:book", "c:my_booking"}))
async def coming_soon(callback: CallbackQuery) -> None:
    stage = 3 if callback.data == "c:book" else 5
    await callback.answer(texts.COMING_SOON.format(stage=stage), show_alert=True)


@router.message()
async def unknown_message(message: Message) -> None:
    """Любой текст, которого бот не ждёт: подсказка и меню."""
    _, markup = await menu_content(message.from_user.id)
    await message.answer(texts.UNKNOWN_MESSAGE, reply_markup=markup)


@router.callback_query()
async def stale_button(callback: CallbackQuery) -> None:
    """Нажата кнопка, которую уже никто не обрабатывает (например, из старого сообщения).

    Без ответа у кнопки долго крутились бы «часики».
    Этот роутер подключён последним, поэтому сюда попадают нажатия и специалиста, и клиентов.
    """
    await callback.answer(texts.STALE_BUTTON, show_alert=True)
