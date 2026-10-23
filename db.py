"""Работа с базой данных SQLite.

Здесь создаются таблицы и лежат все SQL-запросы бота.
Остальной код не пишет SQL сам, а вызывает функции из этого файла.
"""
from contextlib import asynccontextmanager
from typing import AsyncIterator

import aiosqlite

import texts
from config import now_str, settings

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
async def connect() -> AsyncIterator[aiosqlite.Connection]:
    """Открывает подключение к БД.

    Использование:
        async with db.connect() as conn:
            await conn.execute(...)
    """
    async with aiosqlite.connect(settings.db_path) as conn:
        # Строки из БД можно читать по имени колонки: row["title"]
        conn.row_factory = aiosqlite.Row
        # Без этой команды SQLite не проверяет связи REFERENCES между таблицами
        await conn.execute("PRAGMA foreign_keys = ON")
        yield conn


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
