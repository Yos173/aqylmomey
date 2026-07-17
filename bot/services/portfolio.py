RISK_QUESTIONS = [
    {
        "text": "1/3. На сколько лет вы готовы вложить деньги, не трогая их?",
        "options": [
            ("до 1 года", 1),
            ("1-3 года", 2),
            ("более 3 лет", 3),
        ],
    },
    {
        "text": "2/3. Ваш портфель за месяц упал на 20%. Что вы сделаете?",
        "options": [
            ("продам всё, чтобы не терять больше", 1),
            ("подожду и понаблюдаю", 2),
            ("докуплю ещё, пока дёшево", 3),
        ],
    },
    {
        "text": "3/3. Что для вас важнее?",
        "options": [
            ("сохранить деньги любой ценой", 1),
            ("баланс между риском и доходностью", 2),
            ("максимальная доходность, риск не пугает", 3),
        ],
    },
]

ALLOCATION_MODELS: dict[str, dict[str, float]] = {
    "conservative": {"BND": 0.55, "VTIP": 0.25, "VOO": 0.20},
    "balanced": {"VOO": 0.40, "BND": 0.30, "VXUS": 0.30},
    "aggressive": {"VOO": 0.40, "QQQ": 0.35, "VXUS": 0.15, "GLD": 0.10},
}

PROFILE_TITLES = {
    "conservative": "Консервативный",
    "balanced": "Сбалансированный",
    "aggressive": "Агрессивный",
}

VIRTUAL_CASH_START = 1_000_000.0  # виртуальных тенге


def score_risk_profile(answers: list[int]) -> str:
    total = sum(answers)
    if total <= 4:
        return "conservative"
    if total <= 7:
        return "balanced"
    return "aggressive"
