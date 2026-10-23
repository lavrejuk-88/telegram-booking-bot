"""Главное меню клиента."""
import html

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import db
import texts
from config import settings
from handlers.common import edit_or_send
from keyboards import client as kb

router = Router()


async def menu_content(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Текст и кнопки главного меню. Используется и специалистом («Как видит клиент»)."""
    master = await db.get_master()
    # escape: текст приветствия пишет специалист, и символы вроде '<' не должны ломать разметку
    welcome = html.escape(master["welcome_text"] or texts.DEFAULT_WELCOME)
    return welcome, kb.main_menu(
        has_booking=await db.has_active_booking(user_id),
        is_master=user_id == settings.master_tg_id,
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    # /start всегда возвращает в начало, даже из середины записи
    await state.clear()
    text, markup = await menu_content(message.from_user.id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "c:menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    text, markup = await menu_content(callback.from_user.id)
    await edit_or_send(bot, callback.message.chat.id, callback.message.message_id, text, markup)
    await callback.answer()
