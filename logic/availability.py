"""Свободное время под конкретную услугу: соединяет базу данных и расчёт из slots.py."""
from datetime import date, datetime, timedelta

import db
from config import DB_DATETIME_FORMAT, now, settings
from logic.slots import free_starts


def horizon() -> datetime:
    """Самый поздний момент, на который можно записаться."""
    return now() + timedelta(days=settings.booking_horizon_days)


def _parse(value: str) -> datetime:
    return datetime.strptime(value, DB_DATETIME_FORMAT)


async def free_times(
    duration_min: int, first: date, last: date, exclude_booking_id: int | None = None
) -> dict[date, list[datetime]]:
    """Свободные моменты начала визита по дням, с first по last включительно.

    В ответ попадают только дни, где есть хотя бы одно свободное время.
    exclude_booking_id — запись, которую переносят: её время считается свободным.
    """
    work_by_day = await db.get_intervals(first, last)
    busy_rows = await db.get_busy(first.isoformat(), (last + timedelta(days=1)).isoformat(), exclude_booking_id)
    busy = [(_parse(start), _parse(end)) for start, end in busy_rows]
    earliest, latest = now(), horizon()

    result = {}
    for day, intervals in work_by_day.items():
        work = [(_parse(f"{day} {start}"), _parse(f"{day} {end}")) for start, end in intervals]
        starts = free_starts(work, busy, duration_min, settings.booking_step_min, earliest, latest)
        if starts:
            result[day] = starts
    return result


async def free_days(duration_min: int, exclude_booking_id: int | None = None) -> dict[date, list[datetime]]:
    """Все дни от сегодня до горизонта, где есть свободное время."""
    today = now().date()
    return await free_times(duration_min, today, horizon().date(), exclude_booking_id)


def booking_minutes(booking) -> int:
    """Длительность записи в минутах — по её времени, а не по текущей длительности услуги."""
    return int((_parse(booking["end_at"]) - _parse(booking["start_at"])).total_seconds() // 60)
