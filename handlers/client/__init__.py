"""Хендлеры клиента: всё, что видит обычный пользователь."""
from aiogram import Router

from . import booking, fallback, menu
from .menu import menu_content  # нужно специалисту для «Как видит клиент»

router = Router()

# menu — первым, чтобы /start срабатывал даже посреди записи (а не считался, например, именем);
# fallback — последним, в нём «ловушка» для всего остального.
router.include_router(menu.router)
router.include_router(booking.router)
router.include_router(fallback.router)

__all__ = ["router", "menu_content"]
