"""Точка входа. Запуск: python bot.py"""
import asyncio
import logging
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

import db
import reminders
import texts
from config import settings
from handlers import client, master


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            # Журнал не растёт бесконечно: до 1 МБ, плюс 3 предыдущих файла (bot.log.1 … bot.log.3)
            RotatingFileHandler("bot.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"),
        ],
    )


async def main() -> None:
    setup_logging()
    await db.init_db()

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        # HTML-разметка во всех сообщениях: <b>жирный</b>, <i>курсив</i>
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Порядок важен: сначала роутер специалиста, потом клиента.
    # Сообщение от специалиста обработает его роутер; от остальных — клиентский.
    dp.include_router(master.router)
    dp.include_router(client.router)

    # Команды для кнопки «Меню» рядом с полем ввода
    await bot.set_my_commands([BotCommand(command="start", description=texts.CMD_START_DESCRIPTION)])

    # Пропускаем сообщения, которые пришли, пока бот был выключен
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Бот запущен")

    # Напоминания работают параллельно с ботом и останавливаются вместе с ним
    reminders_task = asyncio.create_task(reminders.run(bot))
    try:
        await dp.start_polling(bot)
    finally:
        reminders_task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен")
