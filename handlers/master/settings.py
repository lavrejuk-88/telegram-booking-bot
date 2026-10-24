"""Раздел «⚙️ Настройки» в меню специалиста: текст приветствия для клиентов."""
import html

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import db
import texts
from handlers.common import edit_or_send, try_delete
from keyboards import master as kb
from states import SettingsForm

router = Router()

WELCOME_MAX = 1000


async def show_settings(bot: Bot, chat_id: int, message_id: int | None, note: str = "") -> None:
    master = await db.get_master()
    welcome = html.escape(master["welcome_text"] or texts.DEFAULT_WELCOME)
    text = texts.SETTINGS.format(welcome=welcome)
    if note:
        text = f"{note}\n\n{text}"
    await edit_or_send(bot, chat_id, message_id, text, kb.settings_menu())


@router.callback_query(F.data == "m:settings")
async def open_settings(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await show_settings(bot, callback.message.chat.id, callback.message.message_id)
    await callback.answer()


@router.callback_query(F.data == "m:reset_welcome")
async def reset_welcome(callback: CallbackQuery, bot: Bot) -> None:
    await db.set_welcome(texts.DEFAULT_WELCOME)
    await show_settings(bot, callback.message.chat.id, callback.message.message_id, note=texts.WELCOME_RESET)
    await callback.answer()


async def ask_welcome(bot: Bot, chat_id: int, state: FSMContext, error: str = "") -> None:
    text = texts.ASK_WELCOME.format(max=WELCOME_MAX)
    if error:
        text += f"\n\n⚠️ {error}"
    await edit_or_send(bot, chat_id, (await state.get_data())["prompt_id"], text, kb.welcome_prompt())


@router.callback_query(F.data == "m:set_welcome")
async def start_edit(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.set_state(SettingsForm.welcome)
    await state.set_data({"prompt_id": callback.message.message_id})
    await ask_welcome(bot, callback.message.chat.id, state)
    await callback.answer()


@router.message(StateFilter(SettingsForm.welcome), F.text)
async def welcome_entered(message: Message, state: FSMContext, bot: Bot) -> None:
    await try_delete(message)
    text = message.text.strip()
    if len(text) > WELCOME_MAX:
        await ask_welcome(bot, message.chat.id, state, error=texts.ERR_WELCOME.format(length=len(text), max=WELCOME_MAX))
        return
    prompt_id = (await state.get_data())["prompt_id"]
    await state.clear()
    await db.set_welcome(text)
    await show_settings(bot, message.chat.id, prompt_id, note=texts.WELCOME_SAVED)


@router.message(StateFilter(SettingsForm.welcome))
async def welcome_not_text(message: Message, state: FSMContext, bot: Bot) -> None:
    await try_delete(message)
    await ask_welcome(bot, message.chat.id, state, error=texts.ERR_NEED_TEXT)
