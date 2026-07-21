from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from scripts.ozon_export import OzonApiError, export_products
from scripts.settings import get_settings
from scripts.telegram_summary import build_summary, split_messages
from utils.logging_config import configure_logging


logger = logging.getLogger(__name__)
SUMMARY_BUTTON = "Сводка"
router = Dispatcher()


def keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=SUMMARY_BUTTON)]], resize_keyboard=True)


@router.message(CommandStart())
async def start(message: Message) -> None:
    logger.info("Bot started by chat_id=%s", message.chat.id)
    await message.answer("Готов прислать текущую сводку по товарам Ozon.", reply_markup=keyboard())


@router.message(F.text == SUMMARY_BUTTON)
async def summary(message: Message) -> None:
    await message.answer("Собираю актуальную сводку…")
    try:
        settings = get_settings()
        products, report_path = await export_products(settings)
        for part in split_messages(build_summary(products, settings.low_stock_threshold)):
            await message.answer(part)
        await message.answer(f"CSV-отчёт сохранён: {report_path.name}")
    except (OzonApiError, ValueError) as error:
        logger.exception("Unable to prepare Ozon summary")
        await message.answer("Не удалось подготовить сводку. Подробности записаны в лог.")


async def main() -> None:
    settings = get_settings(require_ozon_credentials=False)
    configure_logging(settings.reports_dir / "logs")
    if not settings.bot_token:
        raise ValueError("BOT_TOKEN must be configured in .env before starting the bot")
    bot = Bot(settings.bot_token)
    logger.info("Telegram bot polling started")
    await router.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
