"""Проверка того, что ввёл пользователь.

Каждая функция получает текст сообщения и возвращает готовое значение
или выбрасывает InvalidInput с понятным пользователю объяснением.
Здесь нет ничего про Telegram, поэтому функции легко проверять отдельно.
"""
import texts

TITLE_MAX = 40          # длиннее не влезет в кнопку
DESCRIPTION_MAX = 300
DURATION_MIN, DURATION_MAX = 5, 720
PRICE_MAX = 1_000_000


class InvalidInput(ValueError):
    pass


def service_title(text: str) -> str:
    # " ".join(text.split()) убирает лишние пробелы и переносы строк
    title = " ".join(text.split())
    if not 1 <= len(title) <= TITLE_MAX:
        raise InvalidInput(texts.ERR_TITLE.format(max=TITLE_MAX))
    return title


def service_duration(text: str) -> int:
    value = text.strip().lower().removesuffix("мин").strip()
    if not value.isdigit():
        raise InvalidInput(texts.ERR_DURATION.format(min=DURATION_MIN, max=DURATION_MAX))
    minutes = int(value)
    if not DURATION_MIN <= minutes <= DURATION_MAX or minutes % 5:
        raise InvalidInput(texts.ERR_DURATION.format(min=DURATION_MIN, max=DURATION_MAX))
    return minutes


def service_price(text: str) -> int:
    # Принимаем «1500», «1 500», «1500 ₽», «1500 руб»
    value = text.lower().replace(" ", "").replace(" ", "")
    for suffix in ("₽", "руб.", "руб", "р.", "р"):
        value = value.removesuffix(suffix)
    if not value.isdigit() or int(value) > PRICE_MAX:
        raise InvalidInput(texts.ERR_PRICE)
    return int(value)


def service_description(text: str) -> str:
    description = text.strip()
    if len(description) > DESCRIPTION_MAX:
        raise InvalidInput(texts.ERR_DESCRIPTION.format(max=DESCRIPTION_MAX, length=len(description)))
    return description
