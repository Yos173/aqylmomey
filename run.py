import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import load_config
from bot.db import init_db
from bot.handlers import antifraud, budget, invest, start


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    await init_db(config.db_path)

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(start.router)
    dp.include_router(antifraud.router)
    dp.include_router(budget.router)
    dp.include_router(invest.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, config=config)


if __name__ == "__main__":
    asyncio.run(main())
