"""Главное меню специалиста.

Меню можно открыть тремя способами: /start, постоянной кнопкой «🏠 Меню специалиста»
внизу экрана и кнопкой «📋 Открыть меню» под уведомлением. Во всех случаях новое меню
появляется внизу чата, а старое удаляется, чтобы в чате не было двух меню сразу.
"""
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import texts
from handlers import client
from handlers.common import try_delete
from keyboards import master as kb

router = Router()

# id последнего сообщения-меню в чате специалиста. Хранится в памяти:
# после перезапуска бот просто «забудет» старое меню и не удалит его — ничего страшного.
_menu_message: dict[int, int] = {}
_intro_message: dict[int, int] = {}


async def _delete(bot: Bot, chat_id: int, message_id: int | None) -> None:
    if message_id is None:
        return
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest:
        pass  # уже удалено или слишком старое — не важно


async def send_menu(bot: Bot, chat_id: int) -> None:
    """Присылает свежее меню внизу чата и удаляет предыдущее."""
    await _delete(bot, chat_id, _menu_message.pop(chat_id, None))
    sent = await bot.send_message(chat_id, texts.MASTER_MENU, reply_markup=kb.main_menu())
    _menu_message[chat_id] = sent.message_id


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    # Кнопку внизу экрана можно поставить только отдельным сообщением,
    # поэтому сначала короткая подсказка с этой кнопкой, затем само меню
    await _delete(bot, message.chat.id, _intro_message.pop(message.chat.id, None))
    intro = await message.answer(texts.MASTER_MENU_HINT, reply_markup=kb.reply_menu())
    _intro_message[message.chat.id] = intro.message_id
    await send_menu(bot, message.chat.id)


@router.message(F.text == texts.BTN_MASTER_MENU)
async def menu_button(message: Message, state: FSMContext, bot: Bot) -> None:
    """Нажата постоянная кнопка внизу экрана. Работает даже посреди любого диалога."""
    await state.clear()
    await try_delete(message)
    await send_menu(bot, message.chat.id)


@router.callback_query(F.data == "m:open_menu")
async def open_menu_below(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    """Кнопка под уведомлением: само уведомление не трогаем, меню — новым сообщением ниже."""
    await state.clear()
    await send_menu(bot, callback.message.chat.id)
    await callback.answer()


@router.callback_query(F.data == "m:menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(texts.MASTER_MENU, reply_markup=kb.main_menu())
    # Это сообщение теперь и есть меню — запомним, чтобы удалить его, когда появится новое
    _menu_message[callback.message.chat.id] = callback.message.message_id
    await callback.answer()


@router.callback_query(F.data == "m:client_view")
async def client_view(callback: CallbackQuery) -> None:
    text, markup = await client.menu_content(callback.from_user.id)
    await callback.message.edit_text(f"{text}\n\n{texts.CLIENT_VIEW_HINT}", reply_markup=markup)
    await callback.answer()
