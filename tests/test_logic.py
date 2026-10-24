"""Чистая логика без Telegram и базы: расчёт слотов, расписание, проверка ввода, форматирование."""
from datetime import datetime

import pytest

import formatting as fmt
from logic import validation
from logic.schedule import hours_to_intervals, intervals_to_hours
from logic.slots import free_starts

DAY = datetime(2030, 1, 1)


def at(hour: int, minute: int = 0) -> datetime:
    return DAY.replace(hour=hour, minute=minute)


# --- свободное время ---


def test_free_starts_example_from_docs():
    # работа 10–14, запись 11–12, шаг 30, услуга 90 мин → 12:00 и 12:30
    starts = free_starts([(at(10), at(14))], [(at(11), at(12))], 90, 30, at(0), at(23))
    assert starts == [at(12), at(12, 30)]


def test_visit_must_fit_into_working_hours():
    assert free_starts([(at(10), at(11))], [], 90, 30, at(0), at(23)) == []


def test_back_to_back_bookings_are_allowed():
    # запись 10–11; следующий визит может начаться ровно в 11:00
    assert at(11) in free_starts([(at(10), at(13))], [(at(10), at(11))], 60, 30, at(0), at(23))


def test_start_must_be_strictly_after_now_and_within_horizon():
    starts = free_starts([(at(10), at(14))], [], 60, 30, earliest=at(10), latest=at(12))
    assert starts == [at(10, 30), at(11), at(11, 30), at(12)]


def test_several_intervals_with_break():
    starts = free_starts([(at(10), at(12)), (at(13), at(14))], [], 60, 60, at(0), at(23))
    assert starts == [at(10), at(11), at(13)]


# --- расписание: часы ↔ интервалы ---


def test_hours_to_intervals_merges_neighbours():
    assert hours_to_intervals({10, 11, 12, 15, 16}) == [("10:00", "13:00"), ("15:00", "17:00")]
    assert hours_to_intervals([]) == []
    assert hours_to_intervals({21}) == [("21:00", "22:00")]


def test_intervals_to_hours():
    assert intervals_to_hours([("10:00", "14:00"), ("15:00", "16:00")]) == {10, 11, 12, 13, 15}


# --- проверка ввода ---


@pytest.mark.parametrize("text", ["89883800204", "+79883800204", "8 988 380 02 04", "+7 (988) 380-02-04", "9883800204"])
def test_phone_any_russian_format(text):
    assert validation.phone(text) == "+7 988 380-02-04"


def test_phone_foreign_with_plus():
    assert validation.phone("+380 50 123 4567") == "+380501234567"


@pytest.mark.parametrize("text", ["123", "абв", "", "8988"])
def test_phone_invalid(text):
    with pytest.raises(validation.InvalidInput):
        validation.phone(text)


def test_client_name():
    assert validation.client_name("  Анна   Мария ") == "Анна Мария"
    for bad in ("А", "12345", "x" * 51):
        with pytest.raises(validation.InvalidInput):
            validation.client_name(bad)


@pytest.mark.parametrize("text, expected", [("1500", 1500), ("1 500 ₽", 1500), ("2000 руб.", 2000), ("0", 0)])
def test_service_price(text, expected):
    assert validation.service_price(text) == expected


@pytest.mark.parametrize("text", ["abc", "7", "0", "1000", "-30"])
def test_service_duration_invalid(text):
    with pytest.raises(validation.InvalidInput):
        validation.service_duration(text)


def test_service_duration_ok():
    assert validation.service_duration("45 мин") == 45


# --- форматирование ---


def test_formatting():
    assert fmt.duration(90) == "1 ч 30 мин"
    assert fmt.duration(60) == "1 ч"
    assert fmt.duration(45) == "45 мин"
    assert fmt.price(1500) == "1 500 ₽"
    assert fmt.timezone() == "МСК, UTC+3"
    assert fmt.intervals([]) == "выходной"
    assert fmt.intervals([("10:00", "14:00"), ("15:00", "19:00")]) == "10:00–14:00, 15:00–19:00"
