"""Ответ специалисту на текст, которого бот не ждёт. Подключается последним."""
from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.types import Message

import texts
from keyboards import master as kb

router = Router()


# StateFilter(None): ловим текст, только если специалист не посреди какого-то сценария.
# Иначе, например, специалист не смог бы ввести имя, проверяя запись «как клиент».
@router.message(StateFilter(None))
async def unknown_message(message: Message) -> None:
    await message.answer(texts.UNKNOWN_MESSAGE, reply_markup=kb.main_menu())
