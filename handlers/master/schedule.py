"""Раздел «🗓 Расписание» в меню специалиста.

Экраны:
- неделя: 7 дней с рабочими часами, листание, операции с неделей;
- редактор дня: сетка часов-переключателей (тот же редактор и для дней шаблона);
- шаблон недели: обычный график по дням недели.

Пока специалист отмечает часы, черновик хранится в FSM (ключ 'draft'),
а в базу попадает только по кнопке «Сохранить».
"""
from datetime import date, timedelta

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

import db
import formatting as fmt
import texts
from config import now, settings
from handlers.common import edit_or_send
from keyboards import master as kb
from keyboards.master import SchedCb
from logic.schedule import hours_to_intervals, intervals_to_hours, week_days, week_start

router = Router()


def today() -> date:
    return now().date()


def last_day() -> date:
    """Последний день, до которого можно планировать (горизонт записи)."""
    return today() + timedelta(days=settings.booking_horizon_days)


def week_range(monday: date) -> dict:
    """Подписи «26.10 – 01.11» для текстов про неделю."""
    return {"first": f"{monday:%d.%m}", "last": f"{monday + timedelta(days=6):%d.%m}"}


# --- Экраны ---


async def show_week(bot: Bot, chat_id: int, message_id: int | None, monday: date, note: str = "") -> None:
    days = week_days(monday)
    schedule = await db.get_intervals(days[0], days[-1])
    lines = []
    for day in days:
        if day == today():
            mark = texts.WEEK_TODAY_MARK
        elif day < today():
            mark = texts.WEEK_PAST_MARK
        else:
            mark = texts.WEEK_FUTURE_MARK
        lines.append(texts.WEEK_DAY_LINE.format(mark=mark, day=fmt.day_short(day), intervals=fmt.intervals(schedule[day])))
    text = texts.WEEK_VIEW.format(**week_range(monday), days="\n".join(lines))
    if note:
        text = f"{note}\n\n{text}"
    markup = kb.week_view(
        monday, days,
        days_off={day for day in days if not schedule[day]},
        can_prev=monday > week_start(today()),
        can_next=monday < week_start(last_day()),
    )
    await edit_or_send(bot, chat_id, message_id, text, markup)


async def show_template(bot: Bot, chat_id: int, message_id: int | None, note: str = "") -> None:
    template = await db.get_template()
    lines = [
        texts.WEEK_DAY_LINE.format(mark="", day=fmt.WEEKDAYS_SHORT[weekday], intervals=fmt.intervals(template[weekday]))
        for weekday in range(7)
    ]
    text = texts.TEMPLATE_VIEW.format(days="\n".join(lines))
    if note:
        text = f"{note}\n\n{text}"
    await edit_or_send(bot, chat_id, message_id, text, kb.template_view())


async def show_editor(bot: Bot, chat_id: int, message_id: int, draft: dict) -> None:
    if draft["day"]:
        title = fmt.day_full(date.fromisoformat(draft["day"]))
    else:
        title = texts.TEMPLATE_DAY_TITLE.format(weekday=fmt.WEEKDAYS_FULL[draft["weekday"]])
    hours = set(draft["hours"])
    text = texts.DAY_EDITOR.format(title=title, intervals=fmt.intervals(hours_to_intervals(hours)))
    await edit_or_send(bot, chat_id, message_id, text, kb.day_editor(hours))


async def back_from_editor(bot: Bot, chat_id: int, message_id: int, draft: dict, note: str = "") -> None:
    """Из редактора возвращаемся туда, откуда пришли: к неделе этого дня или к шаблону."""
    if draft["day"]:
        await show_week(bot, chat_id, message_id, week_start(date.fromisoformat(draft["day"])), note)
    else:
        await show_template(bot, chat_id, message_id, note)


# --- Неделя и шаблон ---


@router.callback_query(F.data == "m:schedule")
@router.callback_query(SchedCb.filter(F.action == "week"))
async def open_week(callback: CallbackQuery, state: FSMContext, bot: Bot, callback_data: SchedCb | None = None) -> None:
    await state.clear()
    if callback_data and callback_data.day:
        monday = date.fromisoformat(callback_data.day) + timedelta(weeks=callback_data.n)
    else:
        monday = week_start(today())
    # Не даём уйти в прошлое или дальше горизонта (например, по старой кнопке)
    monday = min(max(monday, week_start(today())), week_start(last_day()))
    await show_week(bot, callback.message.chat.id, callback.message.message_id, monday)
    await callback.answer()


@router.callback_query(SchedCb.filter(F.action == "tpl"))
async def open_template(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await show_template(bot, callback.message.chat.id, callback.message.message_id)
    await callback.answer()


# --- Редактор дня ---


@router.callback_query(SchedCb.filter(F.action == "day"))
async def edit_day(callback: CallbackQuery, callback_data: SchedCb, state: FSMContext, bot: Bot) -> None:
    day = date.fromisoformat(callback_data.day)
    if day < today():
        await callback.answer(texts.DAY_PASSED, show_alert=True)
        return
    intervals = (await db.get_intervals(day, day))[day]
    draft = {"day": day.isoformat(), "weekday": None, "hours": sorted(intervals_to_hours(intervals))}
    await state.set_data({"draft": draft})
    await show_editor(bot, callback.message.chat.id, callback.message.message_id, draft)
    await callback.answer()


@router.callback_query(SchedCb.filter(F.action == "tpl_day"))
async def edit_template_day(callback: CallbackQuery, callback_data: SchedCb, state: FSMContext, bot: Bot) -> None:
    template = await db.get_template()
    draft = {"day": None, "weekday": callback_data.n, "hours": sorted(intervals_to_hours(template[callback_data.n]))}
    await state.set_data({"draft": draft})
    await show_editor(bot, callback.message.chat.id, callback.message.message_id, draft)
    await callback.answer()


@router.callback_query(SchedCb.filter(F.action.in_({"hour", "save", "off", "cancel"})))
async def editor_action(callback: CallbackQuery, callback_data: SchedCb, state: FSMContext, bot: Bot) -> None:
    draft = (await state.get_data()).get("draft")
    if draft is None:
        # Черновика нет: кнопка из старого сообщения или бот перезапускали
        await callback.answer(texts.STALE_BUTTON, show_alert=True)
        return
    chat_id, message_id = callback.message.chat.id, callback.message.message_id

    if callback_data.action == "hour":
        hours = set(draft["hours"])
        hours ^= {callback_data.n}  # ^= — «переключить»: был час — убрать, не было — добавить
        draft["hours"] = sorted(hours)
        await state.update_data(draft=draft)
        await show_editor(bot, chat_id, message_id, draft)
        await callback.answer()
        return

    if callback_data.action == "cancel":
        await state.clear()
        await back_from_editor(bot, chat_id, message_id, draft)
        await callback.answer()
        return

    # save или off: сохраняем (для «Сделать выходным» — пустой список часов)
    intervals = hours_to_intervals(draft["hours"]) if callback_data.action == "save" else []
    if draft["day"]:
        await db.set_days({date.fromisoformat(draft["day"]): intervals})
    else:
        await db.set_template_day(draft["weekday"], intervals)
    await state.clear()
    await back_from_editor(bot, chat_id, message_id, draft, note=texts.SCHEDULE_SAVED)
    await callback.answer()


# --- Операции с неделей: сначала подтверждение, потом выполнение ---


@router.callback_query(SchedCb.filter(F.action == "ask"))
async def ask_confirm(callback: CallbackQuery, callback_data: SchedCb, bot: Bot) -> None:
    op = callback_data.op
    monday = date.fromisoformat(callback_data.day)
    if op == "copy":
        text = texts.CONFIRM_COPY_WEEK.format(
            **week_range(monday),
            next_first=week_range(monday + timedelta(weeks=1))["first"],
            next_last=week_range(monday + timedelta(weeks=1))["last"],
        )
    elif op == "apply":
        text = texts.CONFIRM_APPLY_WEEK.format(**week_range(monday))
    else:
        text = texts.CONFIRM_CLEAR_WEEK.format(**week_range(monday))
    await edit_or_send(bot, callback.message.chat.id, callback.message.message_id, text, kb.confirm(op, monday))
    await callback.answer()


@router.callback_query(SchedCb.filter(F.action == "do"))
async def do_operation(callback: CallbackQuery, callback_data: SchedCb, bot: Bot) -> None:
    op = callback_data.op
    chat_id, message_id = callback.message.chat.id, callback.message.message_id
    monday = date.fromisoformat(callback_data.day)
    # Прошедшие дни недели не трогаем
    future_days = [day for day in week_days(monday) if day >= today()]

    if op == "apply":
        template = await db.get_template()
        await db.set_days({day: template[day.weekday()] for day in future_days})
        await show_week(bot, chat_id, message_id, monday, note=texts.DONE_APPLY_WEEK)
    elif op == "copy":
        source = await db.get_intervals(monday, monday + timedelta(days=6))
        await db.set_days({day + timedelta(weeks=1): intervals for day, intervals in source.items()})
        await show_week(bot, chat_id, message_id, monday + timedelta(weeks=1), note=texts.DONE_COPY_WEEK)
    elif op == "clear":
        await db.set_days({day: [] for day in future_days})
        await show_week(bot, chat_id, message_id, monday, note=texts.DONE_CLEAR_WEEK)
    await callback.answer()
