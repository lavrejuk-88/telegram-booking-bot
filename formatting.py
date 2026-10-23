"""Красивый вывод для сообщений: длительность, цена, даты, интервалы."""
from datetime import date

import texts

WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
WEEKDAYS_FULL = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]


def day_short(day: date) -> str:
    """'Чт 05.11'"""
    return f"{WEEKDAYS_SHORT[day.weekday()]} {day:%d.%m}"


def day_full(day: date) -> str:
    """'Чт, 05.11.2026'"""
    return f"{WEEKDAYS_SHORT[day.weekday()]}, {day:%d.%m.%Y}"


def intervals(items: list[tuple[str, str]]) -> str:
    """[('10:00', '14:00'), ('15:00', '19:00')] → '10:00–14:00, 15:00–19:00'"""
    if not items:
        return texts.DAY_OFF
    return ", ".join(f"{start}–{end}" for start, end in items)


def duration(minutes: int) -> str:
    """90 → '1 ч 30 мин', 60 → '1 ч', 45 → '45 мин'."""
    hours, mins = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} ч")
    if mins:
        parts.append(f"{mins} мин")
    return " ".join(parts)


def price(rubles: int) -> str:
    """1500 → '1 500 ₽'. Пробел неразрывный, чтобы ₽ не переносился на новую строку."""
    return f"{rubles:,}".replace(",", " ") + " ₽"
