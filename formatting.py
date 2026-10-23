"""Красивый вывод чисел для сообщений: длительность, цена."""


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
