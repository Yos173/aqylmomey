from bot.db import get_user_stats
from bot.services.market_data import INSTRUMENTS

_LOCAL_TICKERS = frozenset(t for t, info in INSTRUMENTS.items() if info["category"] == "local")

BADGE_DEFINITIONS = [
    {
        "id": "antifraud_expert",
        "title": "Антифрод-эксперт",
        "icon": "🛡",
        "description": "Проверить 5 сообщений на признаки мошенничества",
        "check": lambda stats: stats["fraud_checks_count"] >= 5,
    },
    {
        "id": "budget_practitioner",
        "title": "Бюджетный практик",
        "icon": "💰",
        "description": "Записать 10 операций в бюджете",
        "check": lambda stats: stats["transactions_count"] >= 10,
    },
    {
        "id": "investor",
        "title": "Инвестор",
        "icon": "📈",
        "description": "Собрать инвестиционный портфель",
        "check": lambda stats: stats["has_portfolio"],
    },
    {
        "id": "financial_genius",
        "title": "Финансовый гений",
        "icon": "🧠",
        "description": "Пройти финансовый IQ-квиз минимум на 80%",
        "check": lambda stats: stats["best_quiz_ratio"] >= 0.8,
    },
    {
        "id": "kazakhstani",
        "title": "Казахстанец",
        "icon": "🇰🇿",
        "description": "Купить хотя бы один казахстанский инструмент (Kaspi.kz, Halyk Bank, Kazatomprom)",
        "check": lambda stats: bool(stats["held_tickers"] & _LOCAL_TICKERS),
    },
]


async def compute_badges(db_path: str, user_id: int) -> list[dict]:
    stats = await get_user_stats(db_path, user_id)
    return [
        {
            "id": badge["id"],
            "title": badge["title"],
            "icon": badge["icon"],
            "description": badge["description"],
            "earned": bool(badge["check"](stats)),
        }
        for badge in BADGE_DEFINITIONS
    ]
