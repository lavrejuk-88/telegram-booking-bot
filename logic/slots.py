"""Расчёт свободного времени для записи.

Чистая логика без Telegram и базы данных: на вход — рабочие интервалы и занятые отрезки,
на выход — список моментов, с которых можно начать визит.

Пример: работа 10:00–14:00, запись 11:00–12:00, шаг 30 мин, услуга 90 мин.
Кандидаты: 10:00 (до 11:30 — пересекается), 10:30 (до 12:00 — пересекается),
11:00, 11:30 (пересекаются), 12:00 (до 13:30 — подходит), 12:30 (до 14:00 — подходит),
13:00 (до 14:30 — не влезает в рабочее время). Итог: 12:00 и 12:30.
"""
from datetime import datetime, timedelta

Span = tuple[datetime, datetime]  # отрезок времени: (начало, конец)


def overlaps(a: Span, b: Span) -> bool:
    """Пересекаются ли отрезки. Встык (одна запись кончается в 12:00, другая начинается в 12:00) — не пересечение."""
    return a[0] < b[1] and b[0] < a[1]


def free_starts(
    work: list[Span],
    busy: list[Span],
    duration_min: int,
    step_min: int,
    earliest: datetime,
    latest: datetime,
) -> list[datetime]:
    """Свободные моменты начала визита.

    work      — рабочие интервалы специалиста;
    busy      — уже занятые отрезки (активные записи);
    earliest  — начинать можно строго позже этого момента (обычно «сейчас»);
    latest    — и не позже этого момента (горизонт записи).
    """
    duration = timedelta(minutes=duration_min)
    step = timedelta(minutes=step_min)
    result = []
    for work_start, work_end in sorted(work):
        start = work_start
        while start + duration <= work_end:  # визит должен целиком влезть в рабочее время
            visit = (start, start + duration)
            if earliest < start <= latest and not any(overlaps(visit, b) for b in busy):
                result.append(start)
            start += step
    return result
