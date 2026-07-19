import asyncio

import yfinance as yf

# Реальные биржевые инструменты — цены настоящие (через yfinance, без API-ключа),
# деньги пользователя виртуальные. category: "fund" (биржевой фонд) или "stock" (акция).
INSTRUMENTS: dict[str, dict[str, str]] = {
    "VOO": {"name": "Vanguard S&P 500 ETF", "category": "fund"},
    "QQQ": {"name": "Invesco QQQ (Nasdaq-100)", "category": "fund"},
    "VXUS": {"name": "Vanguard Total International Stock ETF", "category": "fund"},
    "BND": {"name": "Vanguard Total Bond Market ETF", "category": "fund"},
    "VTIP": {"name": "Vanguard Short-Term Inflation-Protected Securities ETF", "category": "fund"},
    "GLD": {"name": "SPDR Gold Shares", "category": "fund"},
    "AAPL": {"name": "Apple Inc.", "category": "stock"},
    "MSFT": {"name": "Microsoft Corp.", "category": "stock"},
    "GOOGL": {"name": "Alphabet Inc. (Google)", "category": "stock"},
    "AMZN": {"name": "Amazon.com Inc.", "category": "stock"},
    "TSLA": {"name": "Tesla Inc.", "category": "stock"},
    "NVDA": {"name": "NVIDIA Corp.", "category": "stock"},
    # Казахстанские компании — Kaspi.kz торгуется напрямую на NASDAQ (IPO январь 2024),
    # Halyk Bank и Kazatomprom — через GDR на Лондонской бирже (доступны в yfinance с суффиксом .L).
    "KSPI": {"name": "Kaspi.kz", "category": "local"},
    "HSBK.L": {"name": "Halyk Bank", "category": "local"},
    "KAP.L": {"name": "Kazatomprom", "category": "local"},
}

CATEGORY_TITLES = {"fund": "Фонды (ETF)", "stock": "Акции", "local": "🇰🇿 Казахстан"}

TICKER_NAMES = {ticker: info["name"] for ticker, info in INSTRUMENTS.items()}


def tickers_by_category(category: str) -> list[str]:
    return [ticker for ticker, info in INSTRUMENTS.items() if info["category"] == category]


def _fetch_quote_sync(ticker: str) -> dict | None:
    data = yf.Ticker(ticker).history(period="5d")
    if data.empty:
        return None
    closes = data["Close"]
    price = float(closes.iloc[-1])
    prev = float(closes.iloc[-2]) if len(closes) > 1 else price
    change_pct = ((price - prev) / prev * 100) if prev else 0.0
    return {"price": price, "change_pct": change_pct}


async def get_quote(ticker: str) -> dict | None:
    """Текущая цена + изменение за последний торговый день, в процентах."""
    return await asyncio.to_thread(_fetch_quote_sync, ticker)


async def get_quotes(tickers: list[str]) -> dict[str, dict | None]:
    results = await asyncio.gather(*(get_quote(t) for t in tickers))
    return dict(zip(tickers, results))


async def get_price(ticker: str) -> float | None:
    quote = await get_quote(ticker)
    return quote["price"] if quote else None


async def get_prices(tickers: list[str]) -> dict[str, float | None]:
    quotes = await get_quotes(tickers)
    return {ticker: (quote["price"] if quote else None) for ticker, quote in quotes.items()}


def _fetch_history_sync(ticker: str, period: str) -> list[dict] | None:
    data = yf.Ticker(ticker).history(period=period)
    if data.empty:
        return None
    return [
        {"time": index.strftime("%Y-%m-%d"), "value": float(row["Close"])} for index, row in data.iterrows()
    ]


async def get_history(ticker: str, period: str = "3mo") -> list[dict] | None:
    """История цен закрытия для графика: [{"time": "YYYY-MM-DD", "value": price}, ...]."""
    return await asyncio.to_thread(_fetch_history_sync, ticker, period)
