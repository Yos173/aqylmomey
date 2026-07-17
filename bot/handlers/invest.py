from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.config import Config
from bot.db import add_holding, create_portfolio, get_holdings, get_portfolio
from bot.keyboards import back_to_menu, invest_menu, risk_quiz_question
from bot.services.market_data import TICKER_NAMES, get_prices
from bot.services.portfolio import (
    ALLOCATION_MODELS,
    PROFILE_TITLES,
    RISK_QUESTIONS,
    VIRTUAL_CASH_START,
    score_risk_profile,
)
from bot.states import InvestStates

router = Router(name="invest")

DISCLAIMER = (
    "\n\n⚠️ Это обучающая симуляция на реальных рыночных данных, но с виртуальными деньгами. "
    "Это не инвестиционная рекомендация."
)


@router.callback_query(F.data == "menu:invest")
async def cb_open_invest(callback: CallbackQuery, config: Config) -> None:
    portfolio = await get_portfolio(config.db_path, callback.from_user.id)
    await callback.message.edit_text(
        "📈 Инвест-симулятор." + DISCLAIMER,
        reply_markup=invest_menu(has_portfolio=portfolio is not None),
    )
    await callback.answer()


@router.callback_query(F.data == "invest:quiz")
async def cb_start_quiz(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(InvestStates.quiz_in_progress)
    await state.update_data(answers=[])
    await callback.message.edit_text(RISK_QUESTIONS[0]["text"], reply_markup=risk_quiz_question(0))
    await callback.answer()


@router.callback_query(InvestStates.quiz_in_progress, F.data.startswith("quiz:"))
async def cb_quiz_answer(callback: CallbackQuery, state: FSMContext, config: Config) -> None:
    _, idx_str, value_str = callback.data.split(":")
    question_index = int(idx_str)
    value = int(value_str)

    data = await state.get_data()
    answers: list[int] = data.get("answers", [])
    answers.append(value)
    await state.update_data(answers=answers)

    next_index = question_index + 1
    if next_index < len(RISK_QUESTIONS):
        await callback.message.edit_text(RISK_QUESTIONS[next_index]["text"], reply_markup=risk_quiz_question(next_index))
        await callback.answer()
        return

    profile = score_risk_profile(answers)
    allocation = ALLOCATION_MODELS[profile]

    await callback.message.edit_text("Считаю портфель по текущим рыночным ценам...")

    prices = await get_prices(list(allocation.keys()))
    await create_portfolio(config.db_path, callback.from_user.id, profile, VIRTUAL_CASH_START)

    lines = [
        f"✅ Ваш риск-профиль: <b>{PROFILE_TITLES[profile]}</b>",
        f"Стартовый виртуальный капитал: {VIRTUAL_CASH_START:,.0f} тенге".replace(",", " "),
        "\nМодельный портфель (реальные цены на момент покупки):",
    ]
    for ticker, weight in allocation.items():
        price = prices.get(ticker)
        if price is None:
            lines.append(f"• {ticker} ({TICKER_NAMES.get(ticker, ticker)}) — {weight:.0%}, цена недоступна")
            continue
        cash_alloc = VIRTUAL_CASH_START * weight
        shares = cash_alloc / price
        await add_holding(config.db_path, callback.from_user.id, ticker, shares, price)
        lines.append(
            f"• {ticker} ({TICKER_NAMES.get(ticker, ticker)}) — {weight:.0%} = {cash_alloc:,.0f} по цене ${price:.2f}".replace(",", " ")
        )

    lines.append(DISCLAIMER)
    await callback.message.answer("\n".join(lines), reply_markup=invest_menu(has_portfolio=True))
    await state.clear()


@router.callback_query(F.data == "invest:portfolio")
async def cb_show_portfolio(callback: CallbackQuery, config: Config) -> None:
    portfolio = await get_portfolio(config.db_path, callback.from_user.id)
    holdings = await get_holdings(config.db_path, callback.from_user.id)
    if portfolio is None or not holdings:
        await callback.message.edit_text(
            "У вас ещё нет портфеля. Пройдите риск-квиз.",
            reply_markup=invest_menu(has_portfolio=False),
        )
        await callback.answer()
        return

    tickers = [h["ticker"] for h in holdings]
    current_prices = await get_prices(tickers)

    lines = [f"📊 Риск-профиль: <b>{PROFILE_TITLES[portfolio['risk_profile']]}</b>\n"]
    total_buy_value = 0.0
    total_current_value = 0.0
    for holding in holdings:
        ticker = holding["ticker"]
        buy_value = holding["shares"] * holding["buy_price"]
        current_price = current_prices.get(ticker)
        current_value = holding["shares"] * current_price if current_price else buy_value
        total_buy_value += buy_value
        total_current_value += current_value
        pnl_pct = ((current_value - buy_value) / buy_value * 100) if buy_value else 0.0
        arrow = "🟢" if pnl_pct >= 0 else "🔴"
        lines.append(
            f"{arrow} {ticker}: {current_value:,.0f} (было {buy_value:,.0f}), {pnl_pct:+.1f}%".replace(",", " ")
        )

    total_pnl_pct = ((total_current_value - total_buy_value) / total_buy_value * 100) if total_buy_value else 0.0
    lines.append(f"\n<b>Итого: {total_current_value:,.0f} тенге ({total_pnl_pct:+.1f}%)</b>".replace(",", " "))
    lines.append(DISCLAIMER)

    await callback.message.edit_text("\n".join(lines), reply_markup=invest_menu(has_portfolio=True))
    await callback.answer()
