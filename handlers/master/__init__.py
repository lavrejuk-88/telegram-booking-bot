"""Хендлеры специалиста.

Фильтр стоит на общем роутере, поэтому он защищает все вложенные роутеры:
сообщения и нажатия от других пользователей сюда не попадают вообще.
"""
from aiogram import F, Router

from config import settings

from . import menu

router = Router()
router.message.filter(F.from_user.id == settings.master_tg_id)
router.callback_query.filter(F.from_user.id == settings.master_tg_id)

# menu подключается последним: в нём «ловушка» для любого текста
router.include_router(menu.router)
