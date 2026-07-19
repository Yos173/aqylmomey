from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.db import (
    add_holding,
    adjust_virtual_cash,
    create_portfolio,
    ensure_portfolio,
    get_holdings,
    get_portfolio,
    replace_holding,
)
from bot.keyboards import back_to_menu, instrument_card, instrument_list, invest_menu, markets_menu, risk_quiz_question
from bot.services.market_data import CATEGORY_TITLES, INSTRUMENTS, TICKER_NAMES, get_prices, get_quote, get_quotes, tickers_by_category
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


def _parse_sell_amount(text: str, held_shares: float) -> float | None:
    """Парсит ввод пользователя при продаже: число штук или 'всё'/'все'/'all'. None — некорректный ввод."""
    normalized = text.strip().lower()
    if normalized in ("все", "всё", "all"):
        return held_shares
    try:
        amount = float(normalized.replace(",", "."))
    except ValueError:
        return None
    if amount <= 0 or amount > held_shares + 1e-9:
        return None
    return amount


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


def _profile_title(risk_profile: str) -> str:
    return PROFILE_TITLES.get(risk_profile, "Свой (собран вручную)")


@router.callback_query(F.data == "invest:portfolio")
async def cb_show_portfolio(callback: CallbackQuery, config: Config) -> None:
    portfolio = await get_portfolio(config.db_path, callback.from_user.id)
    if portfolio is None:
        await callback.message.edit_text(
            "У вас ещё нет портфеля. Пройдите риск-квиз или загляните в 📉 Рынки, чтобы купить что-то самостоятельно.",
            reply_markup=invest_menu(has_portfolio=False),
        )
        await callback.answer()
        return

    holdings = await get_holdings(config.db_path, callback.from_user.id)
    lines = [
        f"📊 Риск-профиль: <b>{_profile_title(portfolio['risk_profile'])}</b>",
        f"Свободные тенге: {portfolio['virtual_cash']:,.0f}".replace(",", " "),
    ]

    total_current_value = portfolio["virtual_cash"]
    if not holdings:
        lines.append("\nАктивов пока нет — загляните в 📉 Рынки, чтобы купить.")
    else:
        tickers = [h["ticker"] for h in holdings]
        current_prices = await get_prices(tickers)

        lines.append("")
        total_buy_value = 0.0
        total_positions_value = 0.0
        for holding in holdings:
            ticker = holding["ticker"]
            buy_value = holding["shares"] * holding["buy_price"]
            current_price = current_prices.get(ticker)
            current_value = holding["shares"] * current_price if current_price else buy_value
            total_buy_value += buy_value
            total_positions_value += current_value
            pnl_pct = ((current_value - buy_value) / buy_value * 100) if buy_value else 0.0
            arrow = "🟢" if pnl_pct >= 0 else "🔴"
            lines.append(
                f"{arrow} {ticker} ({holding['shares']:.4f} шт.): {current_value:,.0f} "
                f"(было {buy_value:,.0f}), {pnl_pct:+.1f}%".replace(",", " ")
            )

        total_current_value += total_positions_value
        total_pnl_pct = ((total_positions_value - total_buy_value) / total_buy_value * 100) if total_buy_value else 0.0
        lines.append(f"\nАктивы: {total_positions_value:,.0f} тенге ({total_pnl_pct:+.1f}%)".replace(",", " "))

    lines.append(f"<b>Итого с кэшем: {total_current_value:,.0f} тенге</b>".replace(",", " "))
    lines.append(DISCLAIMER)

    await callback.message.edit_text("\n".join(lines), reply_markup=invest_menu(has_portfolio=True))
    await callback.answer()


@router.callback_query(F.data == "invest:markets")
async def cb_open_markets(callback: CallbackQuery) -> None:
    await callback.message.edit_text("📉 Выберите категорию инструментов:", reply_markup=markets_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("invest:markets:"))
async def cb_show_market_category(callback: CallbackQuery) -> None:
    category = callback.data.rsplit(":", 1)[-1]
    tickers = tickers_by_category(category)
    if not tickers:
        await callback.answer("Категория не найдена", show_alert=True)
        return

    await callback.message.edit_text("Загружаю котировки...")
    quotes = await get_quotes(tickers)

    lines = [f"{CATEGORY_TITLES[category]}\n"]
    for ticker in tickers:
        quote = quotes.get(ticker)
        name = INSTRUMENTS[ticker]["name"]
        if quote is None:
            lines.append(f"{ticker} ({name}) — цена недоступна")
        else:
            arrow = "🟢" if quote["change_pct"] >= 0 else "🔴"
            lines.append(f"{arrow} {ticker} ({name}): ${quote['price']:.2f} ({quote['change_pct']:+.2f}% за день)")
    lines.append("\nВыберите инструмент:")

    await callback.message.edit_text("\n".join(lines), reply_markup=instrument_list(category))
    await callback.answer()


@router.callback_query(F.data.startswith("invest:instrument:"))
async def cb_show_instrument(callback: CallbackQuery, config: Config) -> None:
    ticker = callback.data.rsplit(":", 1)[-1]
    info = INSTRUMENTS.get(ticker)
    if info is None:
        await callback.answer("Инструмент не найден", show_alert=True)
        return

    quote = await get_quote(ticker)
    holdings = await get_holdings(config.db_path, callback.from_user.id)
    held_shares = sum(h["shares"] for h in holdings if h["ticker"] == ticker)

    category_label = "Акция" if info["category"] == "stock" else "Фонд (ETF)"
    lines = [f"<b>{ticker}</b> — {info['name']}", f"Тип: {category_label}"]
    if quote is None:
        lines.append("Цена сейчас недоступна, попробуйте позже.")
    else:
        arrow = "🟢" if quote["change_pct"] >= 0 else "🔴"
        lines.append(f"Цена: ${quote['price']:.2f}  {arrow} {quote['change_pct']:+.2f}% за день")
    if held_shares > 1e-9:
        lines.append(f"\nУ вас: {held_shares:.4f} шт.")

    await callback.message.edit_text(
        "\n".join(lines), reply_markup=instrument_card(ticker, held_shares > 1e-9)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("invest:buy:"))
async def cb_start_buy(callback: CallbackQuery, state: FSMContext, config: Config) -> None:
    ticker = callback.data.rsplit(":", 1)[-1]
    if ticker not in INSTRUMENTS:
        await callback.answer("Инструмент не найден", show_alert=True)
        return

    await ensure_portfolio(config.db_path, callback.from_user.id, "manual", VIRTUAL_CASH_START)
    portfolio = await get_portfolio(config.db_path, callback.from_user.id)

    await state.set_state(InvestStates.waiting_for_buy_amount)
    await state.update_data(ticker=ticker)
    await callback.message.edit_text(
        f"Сколько виртуальных тенге потратить на {ticker}?\n"
        f"Доступно: {portfolio['virtual_cash']:,.0f} тенге".replace(",", " "),
        reply_markup=back_to_menu(),
    )
    await callback.answer()


@router.message(InvestStates.waiting_for_buy_amount)
async def handle_buy_amount(message: Message, state: FSMContext, config: Config) -> None:
    data = await state.get_data()
    ticker = data["ticker"]

    try:
        amount = float((message.text or "").strip().replace(",", "."))
    except ValueError:
        await message.answer("Введите число, например: 50000")
        return
    if amount <= 0:
        await message.answer("Сумма должна быть больше нуля")
        return

    portfolio = await get_portfolio(config.db_path, message.from_user.id)
    if portfolio is None or amount > portfolio["virtual_cash"] + 1e-9:
        available = portfolio["virtual_cash"] if portfolio else 0.0
        await message.answer(f"Недостаточно средств. Доступно: {available:,.0f} тенге".replace(",", " "))
        return

    quote = await get_quote(ticker)
    if quote is None:
        await message.answer("Не удалось получить цену, попробуйте позже.")
        await state.clear()
        return
    price = quote["price"]
    new_shares = amount / price

    holdings = await get_holdings(config.db_path, message.from_user.id)
    existing = [h for h in holdings if h["ticker"] == ticker]
    old_shares = sum(h["shares"] for h in existing)
    old_cost = sum(h["shares"] * h["buy_price"] for h in existing)
    total_shares = old_shares + new_shares
    avg_price = (old_cost + amount) / total_shares

    await replace_holding(config.db_path, message.from_user.id, ticker, total_shares, avg_price)
    new_cash = await adjust_virtual_cash(config.db_path, message.from_user.id, -amount)

    await message.answer(
        f"✅ Куплено {new_shares:.4f} {ticker} по ${price:.2f}\n"
        f"Остаток: {new_cash:,.0f} тенге".replace(",", " "),
        reply_markup=invest_menu(has_portfolio=True),
    )
    await state.clear()


@router.callback_query(F.data.startswith("invest:sell:"))
async def cb_start_sell(callback: CallbackQuery, state: FSMContext, config: Config) -> None:
    ticker = callback.data.rsplit(":", 1)[-1]
    holdings = await get_holdings(config.db_path, callback.from_user.id)
    held_shares = sum(h["shares"] for h in holdings if h["ticker"] == ticker)
    if held_shares <= 1e-9:
        await callback.answer("У вас нет этого инструмента", show_alert=True)
        return

    await state.set_state(InvestStates.waiting_for_sell_amount)
    await state.update_data(ticker=ticker)
    await callback.message.edit_text(
        f"Сколько {ticker} продать?\nДоступно: {held_shares:.4f} шт.\n"
        "Отправьте число или «всё», чтобы продать полностью.",
        reply_markup=back_to_menu(),
    )
    await callback.answer()


@router.message(InvestStates.waiting_for_sell_amount)
async def handle_sell_amount(message: Message, state: FSMContext, config: Config) -> None:
    data = await state.get_data()
    ticker = data["ticker"]

    holdings = await get_holdings(config.db_path, message.from_user.id)
    existing = [h for h in holdings if h["ticker"] == ticker]
    held_shares = sum(h["shares"] for h in existing)
    if held_shares <= 1e-9:
        await message.answer("У вас больше нет этого инструмента.")
        await state.clear()
        return
    old_cost = sum(h["shares"] * h["buy_price"] for h in existing)
    avg_price = old_cost / held_shares

    sell_shares = _parse_sell_amount(message.text or "", held_shares)
    if sell_shares is None:
        await message.answer(f"Некорректный ввод. Введите число (доступно {held_shares:.4f} шт.) или «всё».")
        return

    quote = await get_quote(ticker)
    if quote is None:
        await message.answer("Не удалось получить цену, попробуйте позже.")
        await state.clear()
        return

    proceeds = sell_shares * quote["price"]
    remaining_shares = held_shares - sell_shares
    if remaining_shares < 1e-8:
        remaining_shares = 0.0

    await replace_holding(config.db_path, message.from_user.id, ticker, remaining_shares, avg_price)
    new_cash = await adjust_virtual_cash(config.db_path, message.from_user.id, proceeds)

    pnl_pct = ((quote["price"] - avg_price) / avg_price * 100) if avg_price else 0.0
    await message.answer(
        f"✅ Продано {sell_shares:.4f} {ticker} по ${quote['price']:.2f} ({pnl_pct:+.1f}%)\n"
        f"Остаток: {new_cash:,.0f} тенге".replace(",", " "),
        reply_markup=invest_menu(has_portfolio=True),
    )
    await state.clear()
