import pytest

from bot.db import (
    create_web_user,
    get_leaderboard,
    get_radar_stats,
    get_user_stats,
    get_web_user_by_token,
    init_db,
    log_fraud_check,
    record_quiz_score,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    await init_db(path)
    return path


@pytest.mark.anyio
async def test_create_and_lookup_web_user(db_path):
    user = await create_web_user(db_path, "Аружан", "Школа №5", "10")
    assert user["nickname"] == "Аружан"
    assert user["school"] == "Школа №5"
    assert user["id"] >= 1

    looked_up = await get_web_user_by_token(db_path, user["session_token"])
    assert looked_up == {"id": user["id"], "nickname": "Аружан", "school": "Школа №5", "grade": "10"}


@pytest.mark.anyio
async def test_lookup_with_bad_token_returns_none(db_path):
    await create_web_user(db_path, "Аружан", None, None)
    assert await get_web_user_by_token(db_path, "not-a-real-token") is None


@pytest.mark.anyio
async def test_leaderboard_orders_by_best_score_and_filters_by_school(db_path):
    alice = await create_web_user(db_path, "Alice", "Школа A", "10")
    bob = await create_web_user(db_path, "Bob", "Школа B", "11")

    await record_quiz_score(db_path, -alice["id"], 3, 8)
    await record_quiz_score(db_path, -alice["id"], 6, 8)  # improves best score
    await record_quiz_score(db_path, -bob["id"], 5, 8)

    leaderboard = await get_leaderboard(db_path)
    assert [e["nickname"] for e in leaderboard] == ["Alice", "Bob"]
    assert leaderboard[0]["best_score"] == 6

    filtered = await get_leaderboard(db_path, school="Школа B")
    assert [e["nickname"] for e in filtered] == ["Bob"]


@pytest.mark.anyio
async def test_radar_stats_aggregates_verdicts_and_categories(db_path):
    await log_fraud_check(db_path, 1, 80, "high", ["sensitive_info_request", "urgency_pressure"])
    await log_fraud_check(db_path, 1, 10, "low", [])
    await log_fraud_check(db_path, 2, 90, "high", ["sensitive_info_request"])

    stats = await get_radar_stats(db_path)
    assert stats["total_checks"] == 3
    assert stats["verdict_breakdown"] == {"high": 2, "low": 1}
    top_rules = {c["rule"]: c["count"] for c in stats["top_categories"]}
    assert top_rules["sensitive_info_request"] == 2
    assert top_rules["urgency_pressure"] == 1


@pytest.mark.anyio
async def test_get_user_stats_for_badges(db_path):
    stats = await get_user_stats(db_path, 42)
    assert stats == {
        "fraud_checks_count": 0,
        "transactions_count": 0,
        "has_portfolio": False,
        "held_tickers": set(),
        "best_quiz_ratio": 0.0,
    }

    await log_fraud_check(db_path, 42, 10, "low", [])
    await record_quiz_score(db_path, 42, 4, 8)

    stats = await get_user_stats(db_path, 42)
    assert stats["fraud_checks_count"] == 1
    assert stats["best_quiz_ratio"] == 0.5
