import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import MenuButtonWebApp, WebAppInfo

from bot.config import load_config
from bot.db import init_db
from bot.handlers import antifraud, budget, invest, start
from bot.webapp.server import create_app

logger = logging.getLogger(__name__)


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

    # Веб-сервер (сайт) запускается всегда — доступен и локально (для демо), и через Telegram Mini App.
    # WEBAPP_URL управляет только Telegram-специфичной частью (кнопка Mini App / menu button в /start).
    web_app = create_app(config)
    uvicorn_config = uvicorn.Config(web_app, host="0.0.0.0", port=config.webapp_port, log_level="info")
    tasks = [
        dp.start_polling(bot, config=config),
        uvicorn.Server(uvicorn_config).serve(),
    ]
    logger.info("Сайт запущен на порту %s (http://localhost:%s/)", config.webapp_port, config.webapp_port)

    if config.webapp_url:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Открыть AqylMoney", web_app=WebAppInfo(url=config.webapp_url))
        )
        logger.info("Telegram Mini App включён: %s", config.webapp_url)
    else:
        logger.info("WEBAPP_URL не задан — Telegram-бот работает в обычном режиме (инлайн-меню).")

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
