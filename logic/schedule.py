"""Расчёты для расписания: недели, сетка часов, склейка часов в интервалы.

Здесь нет ни Telegram, ни базы данных — только работа с датами и списками.

Интервал — пара строк ('10:00', '14:00'). Расписание дня — список интервалов.
В редакторе дня расписание представлено набором часов: {10, 11, 12, 13} — это 10:00–14:00.
"""
from datetime import date, timedelta

# Сетка часов в редакторе дня: кнопки 07:00 … 21:00 (последний час — 21:00–22:00)
GRID_HOURS = range(7, 22)

Interval = tuple[str, str]


def hours_to_intervals(hours: set[int] | list[int]) -> list[Interval]:
    """{10, 11, 12, 15, 16} → [('10:00', '13:00'), ('15:00', '17:00')]"""
    intervals = []
    start = prev = None
    for hour in sorted(hours):
        if start is None:
            start = prev = hour
        elif hour == prev + 1:
            prev = hour  # час идёт подряд — продлеваем интервал
        else:
            intervals.append((start, prev + 1))
            start = prev = hour
    if start is not None:
        intervals.append((start, prev + 1))
    return [(f"{a:02d}:00", f"{b:02d}:00") for a, b in intervals]


def intervals_to_hours(intervals: list[Interval]) -> set[int]:
    """[('10:00', '13:00')] → {10, 11, 12}"""
    hours = set()
    for start, end in intervals:
        hours.update(range(int(start[:2]), int(end[:2])))
    return hours


def week_start(day: date) -> date:
    """Понедельник той недели, в которую входит day."""
    return day - timedelta(days=day.weekday())


def week_days(monday: date) -> list[date]:
    return [monday + timedelta(days=i) for i in range(7)]
