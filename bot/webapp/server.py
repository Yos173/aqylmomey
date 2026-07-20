from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from bot.config import Config
from bot.db import (
    add_holding,
    add_transaction,
    adjust_virtual_cash,
    create_portfolio,
    create_web_user,
    ensure_portfolio,
    ensure_user,
    get_balance_summary,
    get_holdings,
    get_leaderboard,
    get_portfolio,
    get_radar_stats,
    get_web_user_by_token,
    log_fraud_check,
    record_quiz_score,
    replace_holding,
)
from bot.services.badges import compute_badges
from bot.services.financial_quiz import public_questions, review_quiz, score_quiz
from bot.services.fraud_scoring import VERDICT_TITLES, rule_labels, score_text, score_to_verdict, template_explanation
from bot.services.llm_client import assess_fraud_risk, ask_assistant, transcribe_scam_image
from bot.services.market_data import (
    CATEGORY_TITLES,
    INSTRUMENTS,
    get_history,
    get_prices,
    get_quote,
    get_quotes,
    tickers_by_category,
)
from bot.services.portfolio import (
    ALLOCATION_MODELS,
    PROFILE_TITLES,
    RISK_QUESTIONS,
    VIRTUAL_CASH_START,
    score_risk_profile,
)
from bot.webapp.auth import InitDataError, parse_and_validate_init_data

STATIC_DIR = Path(__file__).parent / "static"


class AntifraudCheckRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class ImageCheckRequest(BaseModel):
    image_base64: str = Field(min_length=1)
    media_type: str = "image/png"


class TransactionRequest(BaseModel):
    kind: str
    category: str = Field(min_length=1, max_length=100)
    amount: float = Field(gt=0)


class QuizRequest(BaseModel):
    answers: list[int]


class FinancialQuizSubmitRequest(BaseModel):
    answers: list[int]


class BuyRequest(BaseModel):
    ticker: str
    amount: float = Field(gt=0)


class SellRequest(BaseModel):
    ticker: str
    shares: float | None = None
    sell_all: bool = False


class RegisterRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=50)
    school: str | None = Field(default=None, max_length=200)
    grade: str | None = Field(default=None, max_length=20)


class AssistantAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


def _risk_profile_title(risk_profile: str) -> str:
    return PROFILE_TITLES.get(risk_profile, "Свой (собран вручную)")


def _serialize_summary(summary: dict) -> dict:
    return {
        "income": summary["income"],
        "expense": summary["expense"],
        "balance": summary["balance"],
        "top_expenses": [{"category": category, "amount": amount} for category, amount in summary["top_expenses"]],
    }


async def _run_antifraud_check(config: Config, user_id: int, text: str) -> dict:
    """Гибридная оценка: rule-based движок + (если есть ключ) независимая оценка Claude по смыслу.

    Берём максимум из двух оценок — так безопаснее для антифрода: если хотя бы один из судей считает
    сообщение опасным, итоговый вердикт должен быть высоким. Без ключа работает чисто на правилах, как раньше.
    """
    result = score_text(text)
    llm_assessment = (
        await assess_fraud_risk(config.anthropic_api_key, text, result) if config.anthropic_api_key else None
    )

    if llm_assessment:
        final_score = max(result.score, llm_assessment["score"])
        final_verdict = score_to_verdict(final_score)
        explanation = llm_assessment["explanation"]
        ai_red_flags = llm_assessment["red_flags"]
        score_source = "rules+ai"
        persisted_rules = list(result.triggered_rules)
        if llm_assessment["score"] > result.score + 15:
            persisted_rules.append("ai_detected")
    else:
        final_score, final_verdict = result.score, result.verdict
        explanation = template_explanation(result)
        ai_red_flags = []
        score_source = "rules"
        persisted_rules = result.triggered_rules

    await log_fraud_check(config.db_path, user_id, final_score, final_verdict, persisted_rules)

    return {
        "score": final_score,
        "verdict": final_verdict,
        "verdict_title": VERDICT_TITLES[final_verdict],
        "explanation": explanation,
        "triggered_rules": rule_labels(result.triggered_rules),
        "ai_red_flags": ai_red_flags,
        "score_source": score_source,
    }


def build_api_router(config: Config) -> APIRouter:
    router = APIRouter(prefix="/api")

    async def current_user(
        x_web_session_token: str = Header(default="", alias="X-Web-Session-Token"),
        x_telegram_init_data: str = Header(default="", alias="X-Telegram-Init-Data"),
    ) -> dict:
        # Веб-сессия (сайт, ник+школа) имеет приоритет; Telegram initData — для Mini App.
        # user_id веб-пользователей хранится как -web_users.id, чтобы не пересекаться с Telegram ID
        # в общих таблицах (см. комментарий в bot/db.py).
        if x_web_session_token:
            web_user = await get_web_user_by_token(config.db_path, x_web_session_token)
            if web_user is None:
                raise HTTPException(status_code=401, detail="недействительный сессионный токен")
            return {
                "id": -web_user["id"],
                "username": web_user["nickname"],
                "source": "web",
                "school": web_user["school"],
                "grade": web_user["grade"],
            }
        if x_telegram_init_data:
            try:
                tg_user = parse_and_validate_init_data(x_telegram_init_data, config.bot_token)
            except InitDataError as exc:
                raise HTTPException(status_code=401, detail=str(exc)) from exc
            return {"id": tg_user["id"], "username": tg_user.get("username"), "source": "telegram"}
        raise HTTPException(status_code=401, detail="нужен X-Web-Session-Token или X-Telegram-Init-Data")

    # ---------- Регистрация на сайте (без пароля) ----------

    @router.post("/auth/register")
    async def auth_register(payload: RegisterRequest) -> dict:
        nickname = payload.nickname.strip()
        if not nickname:
            raise HTTPException(status_code=400, detail="ник не может быть пустым")
        school = (payload.school or "").strip() or None
        grade = (payload.grade or "").strip() or None
        return await create_web_user(config.db_path, nickname, school, grade)

    # ---------- Антифрод ----------

    @router.post("/antifraud/check")
    async def antifraud_check(payload: AntifraudCheckRequest, user: dict = Depends(current_user)) -> dict:
        user_id = user["id"]
        await ensure_user(config.db_path, user_id, user.get("username"))
        return await _run_antifraud_check(config, user_id, payload.text)

    @router.post("/antifraud/check-image")
    async def antifraud_check_image(payload: ImageCheckRequest, user: dict = Depends(current_user)) -> dict:
        if not config.anthropic_api_key:
            raise HTTPException(status_code=400, detail="Эта функция требует ключ Anthropic API")

        transcribed = await transcribe_scam_image(config.anthropic_api_key, payload.image_base64, payload.media_type)
        if not transcribed:
            raise HTTPException(status_code=502, detail="Не удалось распознать текст на изображении")

        user_id = user["id"]
        await ensure_user(config.db_path, user_id, user.get("username"))
        result = await _run_antifraud_check(config, user_id, transcribed)
        result["transcribed_text"] = transcribed
        return result

    # ---------- Фрод-радар (публично) ----------

    @router.get("/radar/stats")
    async def radar_stats() -> dict:
        stats = await get_radar_stats(config.db_path)
        stats["top_categories"] = [
            {"label": rule_labels([item["rule"]])[0], "count": item["count"]} for item in stats["top_categories"]
        ]
        return stats

    # ---------- Бюджет ----------

    @router.post("/budget/transaction")
    async def budget_add_transaction(payload: TransactionRequest, user: dict = Depends(current_user)) -> dict:
        if payload.kind not in ("income", "expense"):
            raise HTTPException(status_code=400, detail="kind должен быть 'income' или 'expense'")
        user_id = user["id"]
        await ensure_user(config.db_path, user_id, user.get("username"))
        await add_transaction(config.db_path, user_id, payload.kind, payload.category, payload.amount)
        summary = await get_balance_summary(config.db_path, user_id)
        return _serialize_summary(summary)

    @router.get("/budget/summary")
    async def budget_summary(user: dict = Depends(current_user)) -> dict:
        summary = await get_balance_summary(config.db_path, user["id"])
        return _serialize_summary(summary)

    # ---------- Инвестиции ----------

    @router.get("/invest/quiz-questions")
    async def quiz_questions() -> dict:
        return {"questions": RISK_QUESTIONS}

    @router.get("/invest/markets")
    async def invest_markets(user: dict = Depends(current_user)) -> dict:
        categories: dict[str, list[dict]] = {}
        for category in CATEGORY_TITLES:
            tickers = tickers_by_category(category)
            quotes = await get_quotes(tickers)
            categories[category] = [
                {
                    "ticker": ticker,
                    "name": INSTRUMENTS[ticker]["name"],
                    "price": (quotes[ticker]["price"] if quotes.get(ticker) else None),
                    "change_pct": (quotes[ticker]["change_pct"] if quotes.get(ticker) else None),
                }
                for ticker in tickers
            ]
        return {"categories": categories, "titles": CATEGORY_TITLES}

    @router.get("/invest/instrument/{ticker}")
    async def invest_instrument(ticker: str, user: dict = Depends(current_user)) -> dict:
        ticker = ticker.upper()
        info = INSTRUMENTS.get(ticker)
        if info is None:
            raise HTTPException(status_code=404, detail="неизвестный тикер")

        quote = await get_quote(ticker)
        holdings = await get_holdings(config.db_path, user["id"])
        held_shares = sum(h["shares"] for h in holdings if h["ticker"] == ticker)

        return {
            "ticker": ticker,
            "name": info["name"],
            "category": info["category"],
            "price": quote["price"] if quote else None,
            "change_pct": quote["change_pct"] if quote else None,
            "held_shares": held_shares,
        }

    @router.get("/invest/instrument/{ticker}/history")
    async def invest_instrument_history(ticker: str, user: dict = Depends(current_user)) -> dict:
        ticker = ticker.upper()
        if ticker not in INSTRUMENTS:
            raise HTTPException(status_code=404, detail="неизвестный тикер")
        points = await get_history(ticker)
        return {"points": points or []}

    @router.get("/invest/portfolio")
    async def invest_portfolio(user: dict = Depends(current_user)) -> dict:
        user_id = user["id"]
        portfolio = await get_portfolio(config.db_path, user_id)
        if portfolio is None:
            return {"has_portfolio": False}

        holdings = await get_holdings(config.db_path, user_id)
        tickers = [h["ticker"] for h in holdings]
        prices = await get_prices(tickers) if tickers else {}

        holdings_out = []
        total_positions_value = 0.0
        for holding in holdings:
            ticker = holding["ticker"]
            price = prices.get(ticker)
            buy_value = holding["shares"] * holding["buy_price"]
            current_value = holding["shares"] * price if price else buy_value
            total_positions_value += current_value
            holdings_out.append(
                {
                    "ticker": ticker,
                    "name": INSTRUMENTS.get(ticker, {}).get("name", ticker),
                    "shares": holding["shares"],
                    "buy_price": holding["buy_price"],
                    "current_price": price,
                    "current_value": current_value,
                    "buy_value": buy_value,
                    "pnl_pct": ((current_value - buy_value) / buy_value * 100) if buy_value else 0.0,
                }
            )

        return {
            "has_portfolio": True,
            "risk_profile": portfolio["risk_profile"],
            "risk_profile_title": _risk_profile_title(portfolio["risk_profile"]),
            "virtual_cash": portfolio["virtual_cash"],
            "holdings": holdings_out,
            "total_positions_value": total_positions_value,
            "total_value": portfolio["virtual_cash"] + total_positions_value,
        }

    @router.post("/invest/quiz")
    async def invest_quiz(payload: QuizRequest, user: dict = Depends(current_user)) -> dict:
        if len(payload.answers) != len(RISK_QUESTIONS):
            raise HTTPException(status_code=400, detail="неверное количество ответов")

        user_id = user["id"]
        profile = score_risk_profile(payload.answers)
        allocation = ALLOCATION_MODELS[profile]
        prices = await get_prices(list(allocation.keys()))
        await create_portfolio(config.db_path, user_id, profile, VIRTUAL_CASH_START)

        holdings_out = []
        for ticker, weight in allocation.items():
            price = prices.get(ticker)
            if price is None:
                continue
            cash_alloc = VIRTUAL_CASH_START * weight
            shares = cash_alloc / price
            await add_holding(config.db_path, user_id, ticker, shares, price)
            holdings_out.append({"ticker": ticker, "weight": weight, "price": price, "shares": shares})

        return {
            "risk_profile": profile,
            "risk_profile_title": PROFILE_TITLES[profile],
            "virtual_cash_start": VIRTUAL_CASH_START,
            "holdings": holdings_out,
        }

    @router.post("/invest/buy")
    async def invest_buy(payload: BuyRequest, user: dict = Depends(current_user)) -> dict:
        ticker = payload.ticker.upper()
        if ticker not in INSTRUMENTS:
            raise HTTPException(status_code=404, detail="неизвестный тикер")

        user_id = user["id"]
        await ensure_portfolio(config.db_path, user_id, "manual", VIRTUAL_CASH_START)
        portfolio = await get_portfolio(config.db_path, user_id)
        if payload.amount > portfolio["virtual_cash"] + 1e-9:
            raise HTTPException(status_code=400, detail="недостаточно средств")

        quote = await get_quote(ticker)
        if quote is None:
            raise HTTPException(status_code=502, detail="цена сейчас недоступна")
        price = quote["price"]
        new_shares = payload.amount / price

        holdings = await get_holdings(config.db_path, user_id)
        existing = [h for h in holdings if h["ticker"] == ticker]
        old_shares = sum(h["shares"] for h in existing)
        old_cost = sum(h["shares"] * h["buy_price"] for h in existing)
        total_shares = old_shares + new_shares
        avg_price = (old_cost + payload.amount) / total_shares

        await replace_holding(config.db_path, user_id, ticker, total_shares, avg_price)
        new_cash = await adjust_virtual_cash(config.db_path, user_id, -payload.amount)

        return {"ticker": ticker, "bought_shares": new_shares, "price": price, "virtual_cash": new_cash}

    @router.post("/invest/sell")
    async def invest_sell(payload: SellRequest, user: dict = Depends(current_user)) -> dict:
        ticker = payload.ticker.upper()
        user_id = user["id"]

        holdings = await get_holdings(config.db_path, user_id)
        existing = [h for h in holdings if h["ticker"] == ticker]
        held_shares = sum(h["shares"] for h in existing)
        if held_shares <= 1e-9:
            raise HTTPException(status_code=400, detail="нет такой позиции")
        old_cost = sum(h["shares"] * h["buy_price"] for h in existing)
        avg_price = old_cost / held_shares

        sell_shares = held_shares if payload.sell_all else payload.shares
        if sell_shares is None or sell_shares <= 0 or sell_shares > held_shares + 1e-9:
            raise HTTPException(status_code=400, detail="некорректное количество")

        quote = await get_quote(ticker)
        if quote is None:
            raise HTTPException(status_code=502, detail="цена сейчас недоступна")

        proceeds = sell_shares * quote["price"]
        remaining_shares = held_shares - sell_shares
        if remaining_shares < 1e-8:
            remaining_shares = 0.0

        await replace_holding(config.db_path, user_id, ticker, remaining_shares, avg_price)
        new_cash = await adjust_virtual_cash(config.db_path, user_id, proceeds)
        pnl_pct = ((quote["price"] - avg_price) / avg_price * 100) if avg_price else 0.0

        return {
            "ticker": ticker,
            "sold_shares": sell_shares,
            "price": quote["price"],
            "pnl_pct": pnl_pct,
            "virtual_cash": new_cash,
        }

    # ---------- Геймификация: финансовый IQ, бэйджи, лидерборд ----------

    @router.get("/quiz/financial-iq/questions")
    async def financial_iq_questions() -> dict:
        return {"questions": public_questions()}

    @router.post("/quiz/financial-iq/submit")
    async def financial_iq_submit(payload: FinancialQuizSubmitRequest, user: dict = Depends(current_user)) -> dict:
        correct, total = score_quiz(payload.answers)
        await record_quiz_score(config.db_path, user["id"], correct, total)
        badges = await compute_badges(config.db_path, user["id"])
        return {"score": correct, "total": total, "badges": badges, "review": review_quiz(payload.answers)}

    @router.get("/leaderboard")
    async def leaderboard(school: str | None = None) -> dict:
        entries = await get_leaderboard(config.db_path, school=school)
        return {"entries": entries}

    @router.get("/me/badges")
    async def me_badges(user: dict = Depends(current_user)) -> dict:
        return {"badges": await compute_badges(config.db_path, user["id"])}

    # ---------- AI-помощник (коуч + советник по мошенничеству, один чат без истории) ----------

    @router.post("/assistant/ask")
    async def assistant_ask(payload: AssistantAskRequest, user: dict = Depends(current_user)) -> dict:
        if not config.anthropic_api_key:
            raise HTTPException(status_code=400, detail="AI-помощник требует ключ Anthropic API")

        radar = await get_radar_stats(config.db_path)
        top_categories = [rule_labels([item["rule"]])[0] for item in radar["top_categories"]]

        quotes = await get_quotes(list(INSTRUMENTS.keys()))
        market_snapshot = [
            f"{ticker} ({INSTRUMENTS[ticker]['name']}): ${quote['price']:.2f} ({quote['change_pct']:+.1f}%)"
            for ticker, quote in quotes.items()
            if quote is not None
        ]

        answer = await ask_assistant(config.anthropic_api_key, payload.question, top_categories, market_snapshot)
        if answer is None:
            raise HTTPException(status_code=502, detail="AI-помощник сейчас недоступен, попробуйте позже")
        return {"answer": answer}

    return router


def create_app(config: Config) -> FastAPI:
    app = FastAPI(title="AqylMoney WebApp API")
    app.include_router(build_api_router(config))
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def landing() -> FileResponse:
        return FileResponse(STATIC_DIR / "landing.html")

    @app.get("/radar")
    async def radar_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "radar.html")

    @app.get("/app")
    async def app_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app
