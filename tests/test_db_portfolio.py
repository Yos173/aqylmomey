import pytest

from bot.db import (
    adjust_virtual_cash,
    ensure_portfolio,
    get_holdings,
    get_portfolio,
    init_db,
    replace_holding,
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
async def test_ensure_portfolio_creates_once_without_overwriting(db_path):
    await ensure_portfolio(db_path, 1, "manual", 1_000_000.0)
    await ensure_portfolio(db_path, 1, "manual", 999.0)  # must not reset an existing portfolio

    portfolio = await get_portfolio(db_path, 1)
    assert portfolio == {"risk_profile": "manual", "virtual_cash": 1_000_000.0}


@pytest.mark.anyio
async def test_adjust_virtual_cash_updates_balance(db_path):
    await ensure_portfolio(db_path, 1, "manual", 1000.0)

    assert await adjust_virtual_cash(db_path, 1, -300.0) == 700.0
    assert await adjust_virtual_cash(db_path, 1, 50.0) == 750.0


@pytest.mark.anyio
async def test_replace_holding_keeps_a_single_aggregated_lot(db_path):
    await ensure_portfolio(db_path, 1, "manual", 1000.0)

    await replace_holding(db_path, 1, "AAPL", 2.0, 100.0)
    assert await get_holdings(db_path, 1) == [{"ticker": "AAPL", "shares": 2.0, "buy_price": 100.0}]

    # A second buy replaces the lot rather than appending a new row
    await replace_holding(db_path, 1, "AAPL", 3.0, 110.0)
    assert await get_holdings(db_path, 1) == [{"ticker": "AAPL", "shares": 3.0, "buy_price": 110.0}]


@pytest.mark.anyio
async def test_replace_holding_with_zero_shares_removes_position(db_path):
    await ensure_portfolio(db_path, 1, "manual", 1000.0)
    await replace_holding(db_path, 1, "AAPL", 2.0, 100.0)

    await replace_holding(db_path, 1, "AAPL", 0.0, 100.0)
    assert await get_holdings(db_path, 1) == []
