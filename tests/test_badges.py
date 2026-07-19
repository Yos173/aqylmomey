from bot.services.badges import BADGE_DEFINITIONS

_BASE_STATS = {
    "fraud_checks_count": 0,
    "transactions_count": 0,
    "has_portfolio": False,
    "held_tickers": set(),
    "best_quiz_ratio": 0.0,
}


def _check(badge_id: str, stats: dict) -> bool:
    badge = next(b for b in BADGE_DEFINITIONS if b["id"] == badge_id)
    return bool(badge["check"](stats))


def test_no_badges_earned_on_fresh_account():
    for badge in BADGE_DEFINITIONS:
        assert badge["check"](_BASE_STATS) is False


def test_antifraud_expert_threshold():
    assert _check("antifraud_expert", {**_BASE_STATS, "fraud_checks_count": 4}) is False
    assert _check("antifraud_expert", {**_BASE_STATS, "fraud_checks_count": 5}) is True


def test_budget_practitioner_threshold():
    assert _check("budget_practitioner", {**_BASE_STATS, "transactions_count": 9}) is False
    assert _check("budget_practitioner", {**_BASE_STATS, "transactions_count": 10}) is True


def test_investor_requires_portfolio():
    assert _check("investor", {**_BASE_STATS, "has_portfolio": False}) is False
    assert _check("investor", {**_BASE_STATS, "has_portfolio": True}) is True


def test_financial_genius_threshold():
    assert _check("financial_genius", {**_BASE_STATS, "best_quiz_ratio": 0.79}) is False
    assert _check("financial_genius", {**_BASE_STATS, "best_quiz_ratio": 0.8}) is True


def test_kazakhstani_badge_requires_local_ticker():
    assert _check("kazakhstani", {**_BASE_STATS, "held_tickers": {"AAPL"}}) is False
    assert _check("kazakhstani", {**_BASE_STATS, "held_tickers": {"AAPL", "KSPI"}}) is True
    assert _check("kazakhstani", {**_BASE_STATS, "held_tickers": {"HSBK.L"}}) is True
    assert _check("kazakhstani", {**_BASE_STATS, "held_tickers": {"KAP.L"}}) is True
