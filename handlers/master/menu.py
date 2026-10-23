from aiogram import F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import texts
from handlers import client
from keyboards import master as kb

router = Router()

# На каком этапе разработки появится раздел
STAGES = {"m:services": 1, "m:schedule": 2, "m:bookings": 5, "m:settings": 7}


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.MASTER_MENU, reply_markup=kb.main_menu())


@router.callback_query(F.data.in_(STAGES))
async def coming_soon(callback: CallbackQuery) -> None:
    await callback.answer(texts.COMING_SOON.format(stage=STAGES[callback.data]), show_alert=True)


@router.callback_query(F.data == "m:client_view")
async def client_view(callback: CallbackQuery) -> None:
    text, markup = await client.menu_content(callback.from_user.id)
    await callback.message.edit_text(f"{text}\n\n{texts.CLIENT_VIEW_HINT}", reply_markup=markup)
    await callback.answer()


# StateFilter(None): ловим текст, только если специалист не посреди какого-то сценария.
# Иначе, например, специалист не смог бы ввести имя, проверяя запись «как клиент».
@router.message(StateFilter(None))
async def unknown_message(message: Message) -> None:
    await message.answer(texts.UNKNOWN_MESSAGE, reply_markup=kb.main_menu())
