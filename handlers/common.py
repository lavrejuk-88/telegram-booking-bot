"""Помощники для работы с сообщениями, общие для всех хендлеров."""
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message


async def edit_or_send(
    bot: Bot, chat_id: int, message_id: int | None, text: str, markup: InlineKeyboardMarkup | None
) -> int:
    """Меняет сообщение бота на месте, а если не вышло — присылает новое.

    Возвращает id сообщения, которое теперь на экране.
    """
    if message_id is not None:
        try:
            await bot.edit_message_text(text=text, chat_id=chat_id, message_id=message_id, reply_markup=markup)
            return message_id
        except TelegramBadRequest as error:
            # Telegram ругается, если новый текст совпадает со старым. Это не ошибка.
            if "message is not modified" in str(error):
                return message_id
            # Иначе сообщение удалено или слишком старое — пришлём новое
    sent = await bot.send_message(chat_id, text, reply_markup=markup)
    return sent.message_id


async def try_delete(message: Message) -> None:
    """Удаляет сообщение пользователя, чтобы в чате не копился «мусор».

    Если не получилось (например, сообщению больше 48 часов), просто идём дальше.
    """
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
