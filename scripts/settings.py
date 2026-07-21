from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    client_id: str
    api_key: str
    base_url: str
    bot_token: str | None
    telegram_chat_id: str | None
    low_stock_threshold: int
    page_size: int
    batch_size: int
    request_timeout: float
    max_retries: int
    retry_backoff_seconds: float
    reports_dir: Path


def _positive_int(name: str, default: int, maximum: int | None = None) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1 or (maximum is not None and value > maximum):
        raise ValueError(f"{name} must be between 1 and {maximum or 'infinity'}")
    return value


def get_settings(require_ozon_credentials: bool = True) -> Settings:
    client_id = os.getenv("CLIENT_ID", "")
    api_key = os.getenv("API_KEY", "")
    base_url = os.getenv("BASE_URL", "https://api-seller.ozon.ru").rstrip("/")
    if require_ozon_credentials and (not client_id or not api_key):
        raise ValueError("CLIENT_ID and API_KEY must be configured in .env")

    return Settings(
        client_id=client_id,
        api_key=api_key,
        base_url=base_url,
        bot_token=os.getenv("BOT_TOKEN") or None,
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID") or None,
        low_stock_threshold=_positive_int("LOW_STOCK_THRESHOLD", 5),
        page_size=_positive_int("OZON_PAGE_SIZE", 1000, 1000),
        batch_size=_positive_int("OZON_BATCH_SIZE", 1000, 1000),
        request_timeout=float(os.getenv("REQUEST_TIMEOUT", "30")),
        max_retries=_positive_int("MAX_RETRIES", 5),
        retry_backoff_seconds=float(os.getenv("RETRY_BACKOFF_SECONDS", "1")),
        reports_dir=PROJECT_ROOT / "reports",
    )
