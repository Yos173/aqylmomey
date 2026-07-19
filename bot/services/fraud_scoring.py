import re
from dataclasses import dataclass

# Каждое правило — независимый сигнал мошенничества с собственным весом.
# Итоговый score = сумма весов сработавших правил (капается на 100).
_RULES: list[tuple[str, int, list[str]]] = [
    (
        "unrealistic_return",
        30,
        [
            r"\d{2,4}\s?%.{0,20}(доход|прибыл|profit|годовых)",
            r"удво[иж]",
            r"x[2-9]\b",
            r"гарантированн\w* (доход|прибыль)",
            r"пассивный доход без вложени",
        ],
    ),
    (
        "urgency_pressure",
        20,
        [
            r"только сегодня",
            r"успе(й|ть)",
            r"осталось \d+ мест",
            r"предложение действует \d+ (час|минут)",
            r"количество мест ограничено",
        ],
    ),
    (
        "sensitive_info_request",
        35,
        [
            r"код из смс",
            r"cvv",
            r"номер карты",
            r"срок действия карты",
            r"пароль от (личного кабинета|карты|приложения)",
            r"переведи(те)? (деньги )?на карту",
            r"реквизиты (карты|счета)",
            r"код (подтверждения|из) kaspi",
            r"логин.{0,10}(пароль)?.{0,10}kaspi",
            r"данные (карты|счета) kaspi",
        ],
    ),
    (
        "suspicious_link",
        15,
        [
            r"bit\.ly",
            r"clck\.ru",
            r"tinyurl",
            r"\.(xyz|tk|top)\b",
        ],
    ),
    (
        "easy_money_scheme",
        25,
        [
            r"лёгк\w* заработ",
            r"легк\w* заработ",
            r"работа на дому без опыта.{0,15}(доход|\$|тенге|рубл)",
            r"пригласи друга и получи",
            r"финансовая пирамида",
            r"выигр\w*.{0,20}kaspi",
            r"kaspi.{0,20}(розыгрыш\w*|акци\w*|подар\w*)",
        ],
    ),
]

_COMPILED_RULES = [
    (name, weight, [re.compile(p, re.IGNORECASE) for p in patterns])
    for name, weight, patterns in _RULES
]


@dataclass(frozen=True)
class FraudResult:
    score: int
    verdict: str
    triggered_rules: list[str]


_RULE_LABELS = {
    "unrealistic_return": "обещание нереалистичной доходности",
    "urgency_pressure": "искусственное давление срочностью",
    "sensitive_info_request": "запрос конфиденциальных данных или перевода денег",
    "suspicious_link": "подозрительная сокращённая/нетипичная ссылка",
    "easy_money_scheme": "схема 'лёгких денег' / пирамиды",
    "ai_detected": "дополнительно обнаружено ИИ (не по чётким правилам)",
}


def score_to_verdict(score: int) -> str:
    if score < 25:
        return "low"
    if score < 60:
        return "medium"
    return "high"


def score_text(text: str) -> FraudResult:
    triggered: list[str] = []
    total = 0
    for name, weight, patterns in _COMPILED_RULES:
        if any(p.search(text) for p in patterns):
            triggered.append(name)
            total += weight

    score = min(total, 100)
    return FraudResult(score=score, verdict=score_to_verdict(score), triggered_rules=triggered)


def rule_labels(triggered_rules: list[str]) -> list[str]:
    return [_RULE_LABELS.get(name, name) for name in triggered_rules]


VERDICT_TITLES = {
    "low": "🟢 Низкий риск",
    "medium": "🟡 Средний риск — будьте внимательны",
    "high": "🔴 Высокий риск — похоже на мошенничество",
}


def template_explanation(result: FraudResult) -> str:
    if not result.triggered_rules:
        return "Явных признаков мошенничества не обнаружено, но это не гарантия — всегда проверяйте отправителя."
    labels = rule_labels(result.triggered_rules)
    return "Обнаружены признаки:\n" + "\n".join(f"• {label}" for label in labels)
