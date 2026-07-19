import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    anthropic_api_key: str | None
    db_path: str
    webapp_url: str | None
    webapp_port: int


def load_config() -> Config:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN не задан. Скопируйте .env.example в .env и вставьте токен от @BotFather."
        )
    return Config(
        bot_token=token,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        db_path=os.getenv("DB_PATH", "aqylmoney.db"),
        webapp_url=(os.getenv("WEBAPP_URL") or None),
        # Хостинги вроде Render/Railway сами назначают порт через $PORT — уважаем его,
        # если задан, иначе используем WEBAPP_PORT (локальная разработка) или порт по умолчанию.
        webapp_port=int(os.getenv("PORT") or os.getenv("WEBAPP_PORT", "8080")),
    )
