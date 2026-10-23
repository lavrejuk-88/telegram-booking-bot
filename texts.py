"""Все тексты бота в одном месте.

Чтобы адаптировать бота под заказчика, обычно достаточно поменять этот файл.
Тексты в формате HTML: <b>жирный</b>, <i>курсив</i>.
"""

# --- Клиент ---

DEFAULT_WELCOME = (
    "Здравствуйте! 👋\n\n"
    "Здесь можно записаться на визит в пару нажатий: "
    "выберите услугу, день и удобное время."
)

BTN_BOOK = "📅 Записаться"
BTN_WRITE_MASTER = "💬 Написать мастеру"
BTN_MY_BOOKING = "📋 Моя запись"

UNKNOWN_MESSAGE = "Я понимаю только кнопки 🙂 Вот меню:"

# --- Специалист ---

MASTER_MENU = "👋 Меню специалиста"

BTN_M_BOOKINGS = "📒 Записи"
BTN_M_SCHEDULE = "🗓 Расписание"
BTN_M_SERVICES = "🧾 Услуги"
BTN_M_SETTINGS = "⚙️ Настройки"
BTN_M_CLIENT_VIEW = "👀 Как видит клиент"

CLIENT_VIEW_HINT = "<i>Так меню видит клиент. Вернуться в своё меню: /start</i>"

# --- Специалист: услуги ---

SERVICES_LIST = (
    "🧾 <b>Услуги</b>\n\n"
    "Нажмите на услугу, чтобы изменить её.\n"
    "🙈 — услуга скрыта от клиентов."
)
SERVICES_EMPTY = "🧾 <b>Услуги</b>\n\nУслуг пока нет. Добавьте первую!"

BTN_ADD_SERVICE = "➕ Добавить услугу"
BTN_EDIT_TITLE = "✏️ Название"
BTN_EDIT_DURATION = "⏱ Длительность"
BTN_EDIT_PRICE = "💰 Цена"
BTN_EDIT_DESCRIPTION = "📝 Описание"
BTN_HIDE = "🙈 Скрыть от клиентов"
BTN_SHOW = "👁 Показать клиентам"
BTN_UP = "⬆️ Выше"
BTN_DOWN = "⬇️ Ниже"
BTN_TO_LIST = "⬅️ К списку"
BTN_SKIP = "Пропустить ➡️"
BTN_CLEAR_DESCRIPTION = "🗑 Убрать описание"
BTN_CANCEL = "✖️ Отмена"

SERVICE_CARD = (
    "✨ <b>{title}</b>\n\n"
    "⏱ Длительность: {duration}\n"
    "💰 Цена: {price}\n"
    "📝 Описание: {description}\n\n"
    "{status} · место в списке: {position} из {total}"
)
SERVICE_NO_DESCRIPTION = "<i>нет</i>"
SERVICE_VISIBLE = "👁 Видна клиентам"
SERVICE_HIDDEN = "🙈 Скрыта от клиентов"

SERVICE_ADDED = "✅ Услуга добавлена"
SERVICE_SAVED = "✅ Сохранено"
SERVICE_NOT_FOUND = "Такой услуги больше нет"

SERVICE_ADD_HEADER = "➕ <b>Новая услуга</b> · шаг {step} из {total}"
SERVICE_EDIT_HEADER = "✏️ <b>{title}</b>"
SERVICE_PROMPTS = {
    "title": "Введите название услуги.\nНапример: <i>Стандарт</i>",
    "duration_min": "Сколько длится услуга?\nВыберите кнопкой или напишите число минут, например <i>45</i>.",
    "price": "Сколько стоит услуга, в рублях?\nНапример: <i>1500</i>. Если бесплатно — <i>0</i>.",
    "description": "Короткое описание для клиентов: что входит в услугу.",
}

ERR_TITLE = "Название должно быть от 1 до {max} символов."
ERR_DURATION = "Нужно целое число минут от {min} до {max}, кратное 5. Например: 45"
ERR_PRICE = "Нужна цена числом, например 1500."
ERR_DESCRIPTION = "Описание слишком длинное: {length} символов, а можно до {max}."
ERR_NEED_TEXT = "Отправьте ответ текстом."

# --- Общее ---

COMING_SOON = "Этот раздел появится на этапе {stage} 🛠"
STALE_BUTTON = "Эта кнопка устарела. Нажмите /start"

BTN_BACK = "⬅️ Назад"

CMD_START_DESCRIPTION = "Главное меню"
