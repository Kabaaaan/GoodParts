from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from scripts.ozon_export import export_products
from scripts.settings import get_settings
from scripts.telegram_summary import build_summary, split_messages
from utils.logging_config import configure_logging


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.reports_dir / "logs")
    products, report_path = await export_products(settings)
    logging.getLogger(__name__).info("Export completed: %s", report_path)
    if settings.bot_token and settings.telegram_chat_id:
        bot = Bot(settings.bot_token)
        try:
            summary = build_summary(products, settings.low_stock_threshold)
            for part in split_messages(summary):
                await bot.send_message(settings.telegram_chat_id, part)
        finally:
            await bot.session.close()
    else:
        logging.getLogger(__name__).info("Telegram sending skipped: BOT_TOKEN or TELEGRAM_CHAT_ID is not configured")


if __name__ == "__main__":
    asyncio.run(main())
