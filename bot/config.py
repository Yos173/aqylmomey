import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    anthropic_api_key: str | None
    db_path: str


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
    )
