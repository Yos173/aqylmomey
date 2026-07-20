import json
import os
import secrets
from datetime import datetime, timezone

import libsql_client

# Веб-пользователи (сайт) хранятся в web_users, а в общих таблицах (transactions,
# portfolios, holdings, fraud_checks) используют user_id = -web_users.id — отрицательный,
# чтобы не пересекаться с положительными Telegram user_id. Это осознанное решение, а не баг:
# одни и те же функции ниже обслуживают оба источника без изменения схемы общих таблиц.
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
    triggered_rules TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS web_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nickname TEXT NOT NULL,
    school TEXT,
    grade TEXT,
    session_token TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS financial_iq_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    score INTEGER NOT NULL,
    total INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
"""

# Хранилище персистентно только если заданы TURSO_DATABASE_URL/TURSO_AUTH_TOKEN (облачная
# libSQL-база Turso, переживает деплои) — без них используется локальный файл SQLite через
# тот же клиент (для локальной разработки, как раньше). Клиенты кэшируются по ключу подключения,
# чтобы не открывать новое соединение на каждый вызов (важно для сетевого режима) и одновременно
# не путать между собой разные db_path в тестах.
_clients: dict[str, libsql_client.Client] = {}


def _get_client(db_path: str) -> libsql_client.Client:
    turso_url = os.getenv("TURSO_DATABASE_URL")
    key = turso_url or db_path
    client = _clients.get(key)
    if client is None:
        if turso_url:
            client = libsql_client.create_client(turso_url, auth_token=os.getenv("TURSO_AUTH_TOKEN"))
        else:
            client = libsql_client.create_client(f"file:{db_path}")
        _clients[key] = client
    return client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _migrate_fraud_checks_triggered_rules(client: libsql_client.Client) -> None:
    """fraud_checks мог быть создан до появления колонки triggered_rules — добираем её."""
    rs = await client.execute("PRAGMA table_info(fraud_checks)")
    columns = {row[1] for row in rs.rows}
    if "triggered_rules" not in columns:
        await client.execute("ALTER TABLE fraud_checks ADD COLUMN triggered_rules TEXT")


async def init_db(db_path: str) -> None:
    client = _get_client(db_path)
    statements = [s.strip() for s in _SCHEMA.split(";") if s.strip()]
    await client.batch(statements)
    await _migrate_fraud_checks_triggered_rules(client)


async def ensure_user(db_path: str, user_id: int, username: str | None) -> None:
    client = _get_client(db_path)
    await client.execute(
        "INSERT OR IGNORE INTO users (user_id, username, created_at) VALUES (?, ?, ?)",
        (user_id, username, _now()),
    )


async def add_transaction(db_path: str, user_id: int, kind: str, category: str, amount: float) -> None:
    client = _get_client(db_path)
    await client.execute(
        "INSERT INTO transactions (user_id, kind, category, amount, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, kind, category, amount, _now()),
    )


async def get_balance_summary(db_path: str, user_id: int) -> dict:
    client = _get_client(db_path)
    rs = await client.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = ? AND kind = 'income'",
        (user_id,),
    )
    income = rs.rows[0][0]
    rs = await client.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = ? AND kind = 'expense'",
        (user_id,),
    )
    expense = rs.rows[0][0]
    rs = await client.execute(
        """
        SELECT category, SUM(amount) FROM transactions
        WHERE user_id = ? AND kind = 'expense'
        GROUP BY category ORDER BY SUM(amount) DESC LIMIT 5
        """,
        (user_id,),
    )
    top_expenses = [(row[0], row[1]) for row in rs.rows]
    return {
        "income": income,
        "expense": expense,
        "balance": income - expense,
        "top_expenses": top_expenses,
    }


async def create_portfolio(db_path: str, user_id: int, risk_profile: str, virtual_cash: float) -> None:
    client = _get_client(db_path)
    await client.execute(
        "INSERT OR REPLACE INTO portfolios (user_id, risk_profile, virtual_cash, created_at) VALUES (?, ?, ?, ?)",
        (user_id, risk_profile, virtual_cash, _now()),
    )
    await client.execute("DELETE FROM holdings WHERE user_id = ?", (user_id,))


async def ensure_portfolio(db_path: str, user_id: int, default_risk_profile: str, virtual_cash: float) -> None:
    """Создаёт запись портфеля, если её ещё нет. Не трогает существующий кэш/активы."""
    client = _get_client(db_path)
    await client.execute(
        "INSERT OR IGNORE INTO portfolios (user_id, risk_profile, virtual_cash, created_at) VALUES (?, ?, ?, ?)",
        (user_id, default_risk_profile, virtual_cash, _now()),
    )


async def adjust_virtual_cash(db_path: str, user_id: int, delta: float) -> float:
    """Изменяет виртуальный кэш на delta (отрицательный при покупке) и возвращает новый остаток."""
    client = _get_client(db_path)
    await client.execute(
        "UPDATE portfolios SET virtual_cash = virtual_cash + ? WHERE user_id = ?",
        (delta, user_id),
    )
    rs = await client.execute("SELECT virtual_cash FROM portfolios WHERE user_id = ?", (user_id,))
    return rs.rows[0][0] if rs.rows else 0.0


async def get_portfolio(db_path: str, user_id: int) -> dict | None:
    client = _get_client(db_path)
    rs = await client.execute(
        "SELECT risk_profile, virtual_cash FROM portfolios WHERE user_id = ?",
        (user_id,),
    )
    if not rs.rows:
        return None
    row = rs.rows[0]
    return {"risk_profile": row[0], "virtual_cash": row[1]}


async def add_holding(db_path: str, user_id: int, ticker: str, shares: float, buy_price: float) -> None:
    client = _get_client(db_path)
    await client.execute(
        "INSERT INTO holdings (user_id, ticker, shares, buy_price, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, ticker, shares, buy_price, _now()),
    )


async def replace_holding(db_path: str, user_id: int, ticker: str, shares: float, buy_price: float) -> None:
    """Заменяет позицию по тикеру одним агрегированным лотом (используется при покупке/продаже).

    Если shares <= 0, позиция по тикеру просто удаляется.
    """
    client = _get_client(db_path)
    await client.execute("DELETE FROM holdings WHERE user_id = ? AND ticker = ?", (user_id, ticker))
    if shares > 0:
        await client.execute(
            "INSERT INTO holdings (user_id, ticker, shares, buy_price, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, ticker, shares, buy_price, _now()),
        )


async def get_holdings(db_path: str, user_id: int) -> list[dict]:
    client = _get_client(db_path)
    rs = await client.execute(
        "SELECT ticker, shares, buy_price FROM holdings WHERE user_id = ?",
        (user_id,),
    )
    return [{"ticker": r[0], "shares": r[1], "buy_price": r[2]} for r in rs.rows]


async def log_fraud_check(db_path: str, user_id: int, score: int, verdict: str, triggered_rules: list[str]) -> None:
    client = _get_client(db_path)
    await client.execute(
        "INSERT INTO fraud_checks (user_id, score, verdict, triggered_rules, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, score, verdict, json.dumps(triggered_rules), _now()),
    )


# ---------- Веб-пользователи (сайт, без пароля) ----------


async def create_web_user(db_path: str, nickname: str, school: str | None, grade: str | None) -> dict:
    token = secrets.token_urlsafe(24)
    client = _get_client(db_path)
    rs = await client.execute(
        "INSERT INTO web_users (nickname, school, grade, session_token, created_at) VALUES (?, ?, ?, ?, ?)",
        (nickname, school, grade, token, _now()),
    )
    return {
        "id": rs.last_insert_rowid,
        "nickname": nickname,
        "school": school,
        "grade": grade,
        "session_token": token,
    }


async def get_web_user_by_token(db_path: str, session_token: str) -> dict | None:
    client = _get_client(db_path)
    rs = await client.execute(
        "SELECT id, nickname, school, grade FROM web_users WHERE session_token = ?",
        (session_token,),
    )
    if not rs.rows:
        return None
    row = rs.rows[0]
    return {"id": row[0], "nickname": row[1], "school": row[2], "grade": row[3]}


# ---------- Финансовый IQ-квиз и лидерборд ----------


async def record_quiz_score(db_path: str, user_id: int, score: int, total: int) -> None:
    client = _get_client(db_path)
    await client.execute(
        "INSERT INTO financial_iq_scores (user_id, score, total, created_at) VALUES (?, ?, ?, ?)",
        (user_id, score, total, _now()),
    )


async def get_best_quiz_score(db_path: str, user_id: int) -> dict | None:
    client = _get_client(db_path)
    rs = await client.execute(
        "SELECT score, total FROM financial_iq_scores WHERE user_id = ? ORDER BY score DESC LIMIT 1",
        (user_id,),
    )
    if not rs.rows:
        return None
    row = rs.rows[0]
    return {"score": row[0], "total": row[1]}


async def get_leaderboard(db_path: str, school: str | None = None, limit: int = 20) -> list[dict]:
    """Лучший результат квиза на каждого веб-пользователя, отсортировано по убыванию.

    Только веб-пользователи (у Telegram-пользователей нет ника/школы для рейтинга).
    """
    query = """
        SELECT wu.nickname, wu.school, wu.grade, MAX(fi.score) AS best_score, fi.total
        FROM financial_iq_scores fi
        JOIN web_users wu ON fi.user_id = -wu.id
        {where}
        GROUP BY fi.user_id
        ORDER BY best_score DESC
        LIMIT ?
    """
    params: list = []
    where = ""
    if school:
        where = "WHERE wu.school = ?"
        params.append(school)
    params.append(limit)

    client = _get_client(db_path)
    rs = await client.execute(query.format(where=where), params)
    return [{"nickname": r[0], "school": r[1], "grade": r[2], "best_score": r[3], "total": r[4]} for r in rs.rows]


# ---------- Фрод-радар (публичная агрегированная статистика) ----------


async def get_radar_stats(db_path: str, trend_days: int = 14) -> dict:
    client = _get_client(db_path)
    rs = await client.execute("SELECT COUNT(*) FROM fraud_checks")
    total_checks = rs.rows[0][0]

    rs = await client.execute("SELECT verdict, COUNT(*) FROM fraud_checks GROUP BY verdict")
    verdict_breakdown = {row[0]: row[1] for row in rs.rows}

    rs = await client.execute(
        "SELECT substr(created_at, 1, 10) AS day, COUNT(*) FROM fraud_checks GROUP BY day ORDER BY day DESC LIMIT ?",
        (trend_days,),
    )
    trend_by_day = list(reversed([{"day": r[0], "count": r[1]} for r in rs.rows]))

    rs = await client.execute("SELECT triggered_rules FROM fraud_checks WHERE triggered_rules IS NOT NULL")
    category_counts: dict[str, int] = {}
    for (raw,) in rs.rows:
        try:
            rules = json.loads(raw) if raw else []
        except (TypeError, ValueError):
            rules = []
        for rule in rules:
            category_counts[rule] = category_counts.get(rule, 0) + 1

    top_categories = sorted(category_counts.items(), key=lambda item: item[1], reverse=True)[:5]

    return {
        "total_checks": total_checks,
        "verdict_breakdown": verdict_breakdown,
        "trend_by_day": trend_by_day,
        "top_categories": [{"rule": rule, "count": count} for rule, count in top_categories],
    }


# ---------- Статистика пользователя для бэйджей ----------


async def get_user_stats(db_path: str, user_id: int) -> dict:
    client = _get_client(db_path)
    rs = await client.execute("SELECT COUNT(*) FROM fraud_checks WHERE user_id = ?", (user_id,))
    fraud_checks_count = rs.rows[0][0]

    rs = await client.execute("SELECT COUNT(*) FROM transactions WHERE user_id = ?", (user_id,))
    transactions_count = rs.rows[0][0]

    rs = await client.execute("SELECT 1 FROM portfolios WHERE user_id = ?", (user_id,))
    has_portfolio = bool(rs.rows)

    rs = await client.execute("SELECT DISTINCT ticker FROM holdings WHERE user_id = ?", (user_id,))
    held_tickers = {row[0] for row in rs.rows}

    rs = await client.execute(
        "SELECT MAX(score * 1.0 / total) FROM financial_iq_scores WHERE user_id = ? AND total > 0",
        (user_id,),
    )
    best_quiz_ratio = rs.rows[0][0] or 0.0

    return {
        "fraud_checks_count": fraud_checks_count,
        "transactions_count": transactions_count,
        "has_portfolio": has_portfolio,
        "held_tickers": held_tickers,
        "best_quiz_ratio": best_quiz_ratio,
    }
