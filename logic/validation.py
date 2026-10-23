"""Проверка того, что ввёл пользователь.

Каждая функция получает текст сообщения и возвращает готовое значение
или выбрасывает InvalidInput с понятным пользователю объяснением.
Здесь нет ничего про Telegram, поэтому функции легко проверять отдельно.
"""
import re

import texts

TITLE_MAX = 40          # длиннее не влезет в кнопку
DESCRIPTION_MAX = 300
DURATION_MIN, DURATION_MAX = 5, 720
PRICE_MAX = 1_000_000
CLIENT_NAME_MIN, CLIENT_NAME_MAX = 2, 50


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


def client_name(text: str) -> str:
    name = " ".join(text.split())
    if not CLIENT_NAME_MIN <= len(name) <= CLIENT_NAME_MAX or not any(ch.isalpha() for ch in name):
        raise InvalidInput(texts.ERR_CLIENT_NAME.format(min=CLIENT_NAME_MIN, max=CLIENT_NAME_MAX))
    return name


def phone(text: str) -> str:
    """Принимает номер в любом привычном виде и приводит к одному: '+7 900 123-45-67'.

    Подходят: '89001234567', '+79001234567', '+7 (900) 123-45-67', '8 900 123 45 67', '9001234567'.
    Иностранные номера принимаем, если они начинаются с '+': '+380 50 123 4567' → '+380501234567'
    """
    digits = re.sub(r"\D", "", text)  # оставляем только цифры: пробелы, скобки и дефисы не важны
    if len(digits) == 10 and digits[0] == "9":
        digits = "7" + digits
    if len(digits) == 11 and digits[0] in "78":
        return f"+7 {digits[1:4]} {digits[4:7]}-{digits[7:9]}-{digits[9:]}"
    if text.strip().startswith("+") and 10 <= len(digits) <= 15:
        return "+" + digits
    raise InvalidInput(texts.ERR_PHONE)


def service_description(text: str) -> str:
    description = text.strip()
    if len(description) > DESCRIPTION_MAX:
        raise InvalidInput(texts.ERR_DESCRIPTION.format(max=DESCRIPTION_MAX, length=len(description)))
    return description
