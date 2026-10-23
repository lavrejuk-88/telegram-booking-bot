"""Работа с базой данных SQLite.

Здесь создаются таблицы и лежат все SQL-запросы бота.
Остальной код не пишет SQL сам, а вызывает функции из этого файла.
"""
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import AsyncIterator

import aiosqlite

import texts
from config import DB_DATETIME_FORMAT, now_str, settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS masters (
    id           INTEGER PRIMARY KEY,
    tg_id        INTEGER UNIQUE NOT NULL,
    name         TEXT,
    username     TEXT,
    welcome_text TEXT
);

CREATE TABLE IF NOT EXISTS services (
    id           INTEGER PRIMARY KEY,
    master_id    INTEGER NOT NULL REFERENCES masters(id),
    title        TEXT NOT NULL,
    duration_min INTEGER NOT NULL CHECK (duration_min > 0),
    price        INTEGER NOT NULL CHECK (price >= 0),
    description  TEXT,
    is_active    INTEGER NOT NULL DEFAULT 1,
    sort_order   INTEGER NOT NULL DEFAULT 0
);

-- weekday: 0 = понедельник ... 6 = воскресенье
CREATE TABLE IF NOT EXISTS week_template (
    id         INTEGER PRIMARY KEY,
    master_id  INTEGER NOT NULL REFERENCES masters(id),
    weekday    INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    start_time TEXT NOT NULL,
    end_time   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work_intervals (
    id        INTEGER PRIMARY KEY,
    master_id INTEGER NOT NULL REFERENCES masters(id),
    start_at  TEXT NOT NULL,
    end_at    TEXT NOT NULL,
    CHECK (end_at > start_at)
);
CREATE INDEX IF NOT EXISTS work_intervals_time ON work_intervals(master_id, start_at);

CREATE TABLE IF NOT EXISTS clients (
    id         INTEGER PRIMARY KEY,
    tg_id      INTEGER UNIQUE NOT NULL,
    name       TEXT,
    username   TEXT,
    phone      TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bookings (
    id               INTEGER PRIMARY KEY,
    master_id        INTEGER NOT NULL REFERENCES masters(id),
    client_id        INTEGER NOT NULL REFERENCES clients(id),
    service_id       INTEGER NOT NULL REFERENCES services(id),
    start_at         TEXT NOT NULL,
    end_at           TEXT NOT NULL,
    price            INTEGER NOT NULL,
    status           TEXT NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active', 'cancelled', 'rescheduled')),
    created_at       TEXT NOT NULL,
    cancelled_at     TEXT,
    cancelled_by     TEXT CHECK (cancelled_by IN ('client', 'master')),
    cancel_reason    TEXT,
    rescheduled_from INTEGER REFERENCES bookings(id),
    reminded_24h     INTEGER NOT NULL DEFAULT 0,
    reminded_1h      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS bookings_time   ON bookings(master_id, status, start_at);
CREATE INDEX IF NOT EXISTS bookings_client ON bookings(client_id, status);
"""

# (название, длительность в минутах, цена в рублях, описание)
DEMO_SERVICES = [
    ("Экспресс", 30, 900, "Быстрый визит, когда мало времени"),
    ("Стандарт", 60, 1500, "Основная услуга"),
    ("Комплекс", 90, 2200, "Расширенный вариант с дополнительными процедурами"),
    ("Премиум", 120, 3000, "Максимум внимания и времени"),
]

# (день недели, начало, конец): Пн–Пт с перерывом на обед, Сб короткий день, Вс выходной
DEMO_WEEK_TEMPLATE = [
    (day, start, end)
    for day in range(5)
    for start, end in (("10:00", "14:00"), ("15:00", "19:00"))
] + [(5, "11:00", "16:00")]


@asynccontextmanager
async def connect(**kwargs) -> AsyncIterator[aiosqlite.Connection]:
    """Открывает подключение к БД.

    Использование:
        async with db.connect() as conn:
            await conn.execute(...)
    """
    async with aiosqlite.connect(settings.db_path, **kwargs) as conn:
        # Строки из БД можно читать по имени колонки: row["title"]
        conn.row_factory = aiosqlite.Row
        # Без этой команды SQLite не проверяет связи REFERENCES между таблицами
        await conn.execute("PRAGMA foreign_keys = ON")
        yield conn


@asynccontextmanager
async def transaction() -> AsyncIterator[aiosqlite.Connection]:
    """Подключение с «эксклюзивной» транзакцией BEGIN IMMEDIATE.

    Пока транзакция идёт, никто другой не может ничего записать в базу:
    второй запрос на запись подождёт, пока первый закончит.
    Так «проверить, что время свободно» и «сохранить запись» происходят
    как одно неделимое действие, и два клиента не займут одно время.
    Если внутри случится ошибка, все изменения отменятся (ROLLBACK).
    """
    # isolation_level=None: управляем транзакцией сами, Python не начинает её за нас
    async with connect(isolation_level=None) as conn:
        await conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            await conn.execute("ROLLBACK")
            raise
        await conn.execute("COMMIT")


async def init_db() -> None:
    """Создаёт таблицы (если их ещё нет) и запись о специалисте."""
    async with connect() as conn:
        await conn.executescript(SCHEMA)
        await _ensure_master(conn)
        await conn.commit()


async def _ensure_master(conn: aiosqlite.Connection) -> None:
    """Специалист в боте один. При первом запуске создаём его и демо-данные.

    При следующих запусках только обновляем tg_id и username из .env:
    вдруг их поменяли в настройках.
    """
    cursor = await conn.execute("SELECT id FROM masters LIMIT 1")
    row = await cursor.fetchone()
    if row is not None:
        await conn.execute(
            "UPDATE masters SET tg_id = ?, username = ? WHERE id = ?",
            (settings.master_tg_id, settings.master_username, row["id"]),
        )
        return

    cursor = await conn.execute(
        "INSERT INTO masters (tg_id, username, welcome_text) VALUES (?, ?, ?)",
        (settings.master_tg_id, settings.master_username, texts.DEFAULT_WELCOME),
    )
    master_id = cursor.lastrowid

    await conn.executemany(
        "INSERT INTO services (master_id, title, duration_min, price, description, sort_order)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [
            (master_id, title, duration, price, description, order)
            for order, (title, duration, price, description) in enumerate(DEMO_SERVICES)
        ],
    )
    await conn.executemany(
        "INSERT INTO week_template (master_id, weekday, start_time, end_time) VALUES (?, ?, ?, ?)",
        [(master_id, day, start, end) for day, start, end in DEMO_WEEK_TEMPLATE],
    )


async def get_master() -> aiosqlite.Row:
    async with connect() as conn:
        cursor = await conn.execute("SELECT * FROM masters LIMIT 1")
        return await cursor.fetchone()


# --- Услуги ---

# Поля услуги, которые специалист может менять из бота
SERVICE_FIELDS = {"title", "duration_min", "price", "description"}


async def list_services(only_active: bool = False) -> list[aiosqlite.Row]:
    """Услуги в том порядке, в котором их видит клиент."""
    sql = "SELECT * FROM services"
    if only_active:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY sort_order, id"
    async with connect() as conn:
        cursor = await conn.execute(sql)
        return list(await cursor.fetchall())


async def get_service(service_id: int) -> aiosqlite.Row | None:
    async with connect() as conn:
        cursor = await conn.execute("SELECT * FROM services WHERE id = ?", (service_id,))
        return await cursor.fetchone()


async def add_service(title: str, duration_min: int, price: int, description: str | None) -> int:
    """Добавляет услугу в конец списка и возвращает её id."""
    async with connect() as conn:
        cursor = await conn.execute(
            "INSERT INTO services (master_id, title, duration_min, price, description, sort_order)"
            " VALUES ((SELECT id FROM masters LIMIT 1), ?, ?, ?, ?,"
            "         (SELECT COALESCE(MAX(sort_order), -1) + 1 FROM services))",
            (title, duration_min, price, description),
        )
        await conn.commit()
        return cursor.lastrowid


async def update_service(service_id: int, field: str, value: str | int | None) -> None:
    # Имя колонки нельзя передать через '?', поэтому подставляем его в строку.
    # Это безопасно только потому, что поле сверяется со списком разрешённых.
    if field not in SERVICE_FIELDS:
        raise ValueError(f"Нельзя менять поле {field!r}")
    async with connect() as conn:
        await conn.execute(f"UPDATE services SET {field} = ? WHERE id = ?", (value, service_id))
        await conn.commit()


async def toggle_service(service_id: int) -> None:
    """Скрывает услугу от клиентов или возвращает её."""
    async with connect() as conn:
        await conn.execute("UPDATE services SET is_active = 1 - is_active WHERE id = ?", (service_id,))
        await conn.commit()


async def move_service(service_id: int, step: int) -> None:
    """Сдвигает услугу в списке: step = -1 выше, +1 ниже."""
    async with connect() as conn:
        cursor = await conn.execute("SELECT id FROM services ORDER BY sort_order, id")
        ids = [row["id"] for row in await cursor.fetchall()]
        i = ids.index(service_id)
        j = i + step
        if not 0 <= j < len(ids):
            return  # и так первая (или последняя)
        ids[i], ids[j] = ids[j], ids[i]
        # Перенумеровываем все услуги по порядку: 0, 1, 2...
        await conn.executemany(
            "UPDATE services SET sort_order = ? WHERE id = ?",
            [(order, sid) for order, sid in enumerate(ids)],
        )
        await conn.commit()


# --- Расписание ---
# Интервал — пара строк ('10:00', '14:00'), см. logic/schedule.py


async def get_template() -> dict[int, list[tuple[str, str]]]:
    """Шаблон недели: {0: [('10:00', '14:00'), ...], ..., 6: []}"""
    async with connect() as conn:
        cursor = await conn.execute(
            "SELECT weekday, start_time, end_time FROM week_template ORDER BY weekday, start_time"
        )
        rows = await cursor.fetchall()
    template = {weekday: [] for weekday in range(7)}
    for row in rows:
        template[row["weekday"]].append((row["start_time"], row["end_time"]))
    return template


async def set_template_day(weekday: int, intervals: list[tuple[str, str]]) -> None:
    async with connect() as conn:
        await conn.execute("DELETE FROM week_template WHERE weekday = ?", (weekday,))
        await conn.executemany(
            "INSERT INTO week_template (master_id, weekday, start_time, end_time)"
            " VALUES ((SELECT id FROM masters LIMIT 1), ?, ?, ?)",
            [(weekday, start, end) for start, end in intervals],
        )
        await conn.commit()


async def get_intervals(first: date, last: date) -> dict[date, list[tuple[str, str]]]:
    """Рабочие интервалы с first по last включительно: {date: [('10:00', '14:00'), ...]}"""
    async with connect() as conn:
        cursor = await conn.execute(
            "SELECT start_at, end_at FROM work_intervals"
            " WHERE start_at >= ? AND start_at < ? ORDER BY start_at",
            (first.isoformat(), (last + timedelta(days=1)).isoformat()),
        )
        rows = await cursor.fetchall()
    result = {first + timedelta(days=i): [] for i in range((last - first).days + 1)}
    for row in rows:
        # '2026-11-05 10:00' → дата '2026-11-05' и время '10:00'
        day = date.fromisoformat(row["start_at"][:10])
        result[day].append((row["start_at"][11:], row["end_at"][11:]))
    return result


async def set_days(days: dict[date, list[tuple[str, str]]]) -> None:
    """Заменяет расписание указанных дней. Всё в одной транзакции: либо все дни, либо ни одного.

    Записи клиентов здесь не проверяются — это делает раздел расписания (save_days) до вызова.
    """
    async with connect() as conn:
        for day, intervals in days.items():
            await conn.execute(
                "DELETE FROM work_intervals WHERE start_at >= ? AND start_at < ?",
                (day.isoformat(), (day + timedelta(days=1)).isoformat()),
            )
            await conn.executemany(
                "INSERT INTO work_intervals (master_id, start_at, end_at)"
                " VALUES ((SELECT id FROM masters LIMIT 1), ?, ?)",
                [(f"{day.isoformat()} {start}", f"{day.isoformat()} {end}") for start, end in intervals],
            )
        await conn.commit()


# --- Клиенты ---


async def get_client(tg_id: int) -> aiosqlite.Row | None:
    async with connect() as conn:
        cursor = await conn.execute("SELECT * FROM clients WHERE tg_id = ?", (tg_id,))
        return await cursor.fetchone()


async def save_client(tg_id: int, username: str | None, name: str | None = None, phone: str | None = None) -> None:
    """Создаёт клиента или обновляет его данные. Поля со значением None не меняются."""
    async with connect() as conn:
        await conn.execute(
            "INSERT INTO clients (tg_id, username, name, phone, created_at) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(tg_id) DO UPDATE SET"
            "   username = excluded.username,"
            "   name  = COALESCE(excluded.name, clients.name),"
            "   phone = COALESCE(excluded.phone, clients.phone)",
            (tg_id, username, name, phone, now_str()),
        )
        await conn.commit()


# --- Записи ---


class BookingError(Exception):
    """Записать не получилось. code объясняет почему:

    'taken'       — время заняли, оно прошло или вне рабочего времени;
    'has_booking' — у клиента уже есть будущая запись;
    'service'     — услуга удалена или скрыта;
    'client'      — нет имени или телефона клиента;
    'gone'        — (при переносе) запись уже отменена или прошла.
    """

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# Запись вместе со всем, что нужно показать: клиент, услуга, время
BOOKING_DETAILS = (
    "SELECT b.*, s.title AS service_title,"
    "       c.tg_id AS client_tg_id, c.name AS client_name,"
    "       c.username AS client_username, c.phone AS client_phone"
    " FROM bookings b"
    " JOIN clients c ON c.id = b.client_id"
    " JOIN services s ON s.id = b.service_id"
)


async def get_busy(first: str, last: str, exclude_booking_id: int | None = None) -> list[tuple[str, str]]:
    """Активные записи, которые пересекаются с отрезком [first, last).

    exclude_booking_id — не считать эту запись занятой. Нужно при переносе:
    клиент может сдвинуть свою запись на полчаса, «наехав» на собственное старое время.
    """
    sql = "SELECT start_at, end_at FROM bookings WHERE status = 'active' AND start_at < ? AND end_at > ?"
    params = [last, first]
    if exclude_booking_id is not None:
        sql += " AND id != ?"
        params.append(exclude_booking_id)
    async with connect() as conn:
        cursor = await conn.execute(sql, params)
        return [(row["start_at"], row["end_at"]) for row in await cursor.fetchall()]


async def get_active_booking(client_tg_id: int) -> aiosqlite.Row | None:
    """Будущая активная запись клиента."""
    async with connect() as conn:
        cursor = await conn.execute(
            BOOKING_DETAILS + " WHERE c.tg_id = ? AND b.status = 'active' AND b.start_at > ?"
            " ORDER BY b.start_at LIMIT 1",
            (client_tg_id, now_str()),
        )
        return await cursor.fetchone()


async def list_bookings(first: str, last: str) -> list[aiosqlite.Row]:
    """Активные записи, которые начинаются в отрезке [first, last), по порядку."""
    async with connect() as conn:
        cursor = await conn.execute(
            BOOKING_DETAILS + " WHERE b.status = 'active' AND b.start_at >= ? AND b.start_at < ?"
            " ORDER BY b.start_at",
            (first, last),
        )
        return list(await cursor.fetchall())


async def create_booking(client_tg_id: int, service_id: int, start_at: str, horizon: str) -> int:
    """Создаёт запись и возвращает её id. Если нельзя — BookingError.

    Все проверки повторяются внутри транзакции, даже если клиенту только что
    показали это время как свободное: за секунды до нажатия его мог занять кто-то другой.
    """
    async with transaction() as conn:
        cursor = await conn.execute("SELECT * FROM services WHERE id = ? AND is_active = 1", (service_id,))
        service = await cursor.fetchone()
        if service is None:
            raise BookingError("service")

        cursor = await conn.execute("SELECT * FROM clients WHERE tg_id = ?", (client_tg_id,))
        client = await cursor.fetchone()
        if client is None or not client["name"] or not client["phone"]:
            raise BookingError("client")

        current = now_str()
        cursor = await conn.execute(
            "SELECT 1 FROM bookings WHERE client_id = ? AND status = 'active' AND start_at > ?",
            (client["id"], current),
        )
        if await cursor.fetchone():
            raise BookingError("has_booking")

        start = datetime.strptime(start_at, DB_DATETIME_FORMAT)
        end_at = (start + timedelta(minutes=service["duration_min"])).strftime(DB_DATETIME_FORMAT)
        if not current < start_at <= horizon:
            raise BookingError("taken")

        # Визит целиком внутри одного рабочего интервала?
        cursor = await conn.execute(
            "SELECT 1 FROM work_intervals WHERE start_at <= ? AND end_at >= ?", (start_at, end_at)
        )
        if await cursor.fetchone() is None:
            raise BookingError("taken")

        # Пересекается с чужой записью?
        cursor = await conn.execute(
            "SELECT 1 FROM bookings WHERE status = 'active' AND start_at < ? AND end_at > ?",
            (end_at, start_at),
        )
        if await cursor.fetchone():
            raise BookingError("taken")

        cursor = await conn.execute(
            "INSERT INTO bookings (master_id, client_id, service_id, start_at, end_at, price, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (service["master_id"], client["id"], service_id, start_at, end_at, service["price"], current),
        )
        return cursor.lastrowid


async def get_booking_details(booking_id: int) -> aiosqlite.Row | None:
    async with connect() as conn:
        cursor = await conn.execute(BOOKING_DETAILS + " WHERE b.id = ?", (booking_id,))
        return await cursor.fetchone()


async def cancel_booking(booking_id: int, by: str, reason: str | None = None) -> bool:
    """Отменяет активную запись. by — кто отменил: 'client' или 'master'.

    Возвращает False, если запись уже не активна (например, её только что отменили с другой стороны).
    Запись не удаляется: остаётся в истории со статусом 'cancelled', а время освобождается.
    """
    async with connect() as conn:
        cursor = await conn.execute(
            "UPDATE bookings SET status = 'cancelled', cancelled_at = ?, cancelled_by = ?, cancel_reason = ?"
            " WHERE id = ? AND status = 'active'",
            (now_str(), by, reason, booking_id),
        )
        await conn.commit()
        return cursor.rowcount > 0


async def reschedule_booking(booking_id: int, client_tg_id: int, new_start: str, horizon: str) -> int:
    """Переносит запись на новое время и возвращает id новой записи. Если нельзя — BookingError.

    Старая запись получает статус 'rescheduled', новая ссылается на неё (rescheduled_from).
    Всё в одной транзакции: старое время освобождается только если новое удалось занять.
    Коды ошибок: 'gone' — переносить нечего (запись отменена или уже прошла), 'taken' — время занято.
    """
    async with transaction() as conn:
        current = now_str()
        cursor = await conn.execute(
            "SELECT b.* FROM bookings b JOIN clients c ON c.id = b.client_id"
            " WHERE b.id = ? AND c.tg_id = ? AND b.status = 'active' AND b.start_at > ?",
            (booking_id, client_tg_id, current),
        )
        old = await cursor.fetchone()
        if old is None:
            raise BookingError("gone")

        # Длительность и цена — как в исходной записи, даже если услугу с тех пор изменили
        duration = datetime.strptime(old["end_at"], DB_DATETIME_FORMAT) - datetime.strptime(old["start_at"], DB_DATETIME_FORMAT)
        new_end = (datetime.strptime(new_start, DB_DATETIME_FORMAT) + duration).strftime(DB_DATETIME_FORMAT)
        if not current < new_start <= horizon:
            raise BookingError("taken")

        cursor = await conn.execute(
            "SELECT 1 FROM work_intervals WHERE start_at <= ? AND end_at >= ?", (new_start, new_end)
        )
        if await cursor.fetchone() is None:
            raise BookingError("taken")

        # Пересечение с чужими записями (свою старую не считаем)
        cursor = await conn.execute(
            "SELECT 1 FROM bookings WHERE status = 'active' AND start_at < ? AND end_at > ? AND id != ?",
            (new_end, new_start, booking_id),
        )
        if await cursor.fetchone():
            raise BookingError("taken")

        await conn.execute("UPDATE bookings SET status = 'rescheduled' WHERE id = ?", (booking_id,))
        cursor = await conn.execute(
            "INSERT INTO bookings (master_id, client_id, service_id, start_at, end_at, price, created_at, rescheduled_from)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (old["master_id"], old["client_id"], old["service_id"], new_start, new_end, old["price"], current, booking_id),
        )
        return cursor.lastrowid


async def has_active_booking(client_tg_id: int) -> bool:
    """Есть ли у клиента активная запись в будущем (для кнопки «Моя запись»)."""
    async with connect() as conn:
        cursor = await conn.execute(
            "SELECT 1 FROM bookings b"
            " JOIN clients c ON c.id = b.client_id"
            " WHERE c.tg_id = ? AND b.status = 'active' AND b.start_at > ?"
            " LIMIT 1",
            (client_tg_id, now_str()),
        )
        return await cursor.fetchone() is not None
