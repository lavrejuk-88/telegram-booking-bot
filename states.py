"""Шаги диалогов (FSM).

FSM помнит для каждого пользователя, на каком шаге он сейчас.
Например, бот спросил название услуги, и специалист в состоянии ServiceForm.title:
следующий его текст бот воспримет как название, а не как случайное сообщение.
"""
from aiogram.fsm.state import State, StatesGroup


class BookingForm(StatesGroup):
    """Запись клиента: карточка открыта (card) или бот ждёт имя / телефон."""
    card = State()
    name = State()
    phone = State()


class ServiceForm(StatesGroup):
    """Добавление услуги (все шаги по очереди) или изменение одного поля."""
    title = State()
    duration = State()
    price = State()
    description = State()
