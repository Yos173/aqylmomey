import asyncio

import yfinance as yf

# Реальные биржевые инструменты (глобальные ETF/акции) — цены настоящие,
# деньги пользователя виртуальные. Подобраны без API-ключа через yfinance.
TICKER_NAMES = {
    "VOO": "Vanguard S&P 500 ETF",
    "QQQ": "Invesco QQQ (Nasdaq-100)",
    "VXUS": "Vanguard Total International Stock ETF",
    "BND": "Vanguard Total Bond Market ETF",
    "VTIP": "Vanguard Short-Term Inflation-Protected Securities ETF",
    "GLD": "SPDR Gold Shares",
}


def _fetch_price_sync(ticker: str) -> float | None:
    data = yf.Ticker(ticker).history(period="5d")
    if data.empty:
        return None
    return float(data["Close"].iloc[-1])


async def get_price(ticker: str) -> float | None:
    return await asyncio.to_thread(_fetch_price_sync, ticker)


async def get_prices(tickers: list[str]) -> dict[str, float | None]:
    results = await asyncio.gather(*(get_price(t) for t in tickers))
    return dict(zip(tickers, results))
