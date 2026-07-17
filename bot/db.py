from datetime import datetime, timezone

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
    category TEXT NOT NULL,
    amount REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolios (
    user_id INTEGER PRIMARY KEY,
    risk_profile TEXT NOT NULL,
    virtual_cash REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    shares REAL NOT NULL,
    buy_price REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fraud_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    score INTEGER NOT NULL,
    verdict TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


async def ensure_user(db_path: str, user_id: int, username: str | None) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, created_at) VALUES (?, ?, ?)",
            (user_id, username, _now()),
        )
        await db.commit()


async def add_transaction(db_path: str, user_id: int, kind: str, category: str, amount: float) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO transactions (user_id, kind, category, amount, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, kind, category, amount, _now()),
        )
        await db.commit()


async def get_balance_summary(db_path: str, user_id: int) -> dict:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = ? AND kind = 'income'",
            (user_id,),
        )
        income = (await cursor.fetchone())[0]
        cursor = await db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = ? AND kind = 'expense'",
            (user_id,),
        )
        expense = (await cursor.fetchone())[0]
        cursor = await db.execute(
            """
            SELECT category, SUM(amount) FROM transactions
            WHERE user_id = ? AND kind = 'expense'
            GROUP BY category ORDER BY SUM(amount) DESC LIMIT 5
            """,
            (user_id,),
        )
        top_expenses = await cursor.fetchall()
        return {
            "income": income,
            "expense": expense,
            "balance": income - expense,
            "top_expenses": top_expenses,
        }


async def create_portfolio(db_path: str, user_id: int, risk_profile: str, virtual_cash: float) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO portfolios (user_id, risk_profile, virtual_cash, created_at) VALUES (?, ?, ?, ?)",
            (user_id, risk_profile, virtual_cash, _now()),
        )
        await db.execute("DELETE FROM holdings WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_portfolio(db_path: str, user_id: int) -> dict | None:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT risk_profile, virtual_cash FROM portfolios WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return {"risk_profile": row[0], "virtual_cash": row[1]}


async def add_holding(db_path: str, user_id: int, ticker: str, shares: float, buy_price: float) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO holdings (user_id, ticker, shares, buy_price, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, ticker, shares, buy_price, _now()),
        )
        await db.commit()


async def get_holdings(db_path: str, user_id: int) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT ticker, shares, buy_price FROM holdings WHERE user_id = ?",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [{"ticker": r[0], "shares": r[1], "buy_price": r[2]} for r in rows]


async def log_fraud_check(db_path: str, user_id: int, score: int, verdict: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO fraud_checks (user_id, score, verdict, created_at) VALUES (?, ?, ?, ?)",
            (user_id, score, verdict, _now()),
        )
        await db.commit()
