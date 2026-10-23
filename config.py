"""Настройки бота.

Все значения читаются из файла .env (или из переменных окружения).
В коде нет ни токена, ни других секретов.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # SecretStr не даёт токену случайно попасть в логи: при печати видно '**********'
    bot_token: SecretStr
    master_tg_id: int
    master_username: str

    timezone: str = "Europe/Moscow"
    timezone_label: str = "московское"
    booking_step_min: int = 30
    booking_horizon_days: int = 60
    db_path: str = "bot.db"

    @field_validator("master_username")
    @classmethod
    def strip_at(cls, value: str) -> str:
        # Пишут и '@anna', и 'anna' — храним без '@'
        return value.strip().lstrip("@")


settings = Settings()
TZ = ZoneInfo(settings.timezone)

# Формат, в котором дата и время хранятся в БД: '2026-11-05 14:00'
DB_DATETIME_FORMAT = "%Y-%m-%d %H:%M"


def now() -> datetime:
    """Текущее время в поясе специалиста, без информации о поясе.

    Именно так время хранится в БД, поэтому результат можно
    сравнивать со значениями из таблиц напрямую.
    """
    return datetime.now(TZ).replace(tzinfo=None, second=0, microsecond=0)


def now_str() -> str:
    return now().strftime(DB_DATETIME_FORMAT)
