"""Ответы на то, чего бот не ждёт. Подключается последним."""
from aiogram import Router
from aiogram.types import CallbackQuery, Message

import texts

from .menu import menu_content

router = Router()


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
