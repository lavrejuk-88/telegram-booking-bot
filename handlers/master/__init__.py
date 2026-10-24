"""Хендлеры специалиста.

Фильтр стоит на общем роутере, поэтому он защищает все вложенные роутеры:
сообщения и нажатия от других пользователей сюда не попадают вообще.
"""
from aiogram import F, Router

import config

# config импортируем целиком: в этой папке есть свой модуль settings.py (раздел «Настройки»),
# и `from config import settings` перепутался бы с ним
from . import bookings, fallback, menu, schedule, services, settings

router = Router()
router.message.filter(F.from_user.id == config.settings.master_tg_id)
router.callback_query.filter(F.from_user.id == config.settings.master_tg_id)

# Порядок важен:
# menu — первым, чтобы /start срабатывал даже посреди диалога (а не считался, например, названием услуги);
# fallback — последним, в нём «ловушка» для любого текста.
router.include_router(menu.router)
router.include_router(services.router)
router.include_router(schedule.router)
router.include_router(bookings.router)
router.include_router(settings.router)
router.include_router(fallback.router)
