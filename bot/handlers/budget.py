from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.db import add_transaction, get_balance_summary
from bot.keyboards import back_to_menu, budget_menu
from bot.states import BudgetStates

router = Router(name="budget")

INCOME_PROMPT = "Введите сумму дохода и источник через пробел, например:\n<code>50000 стипендия</code>"
EXPENSE_PROMPT = "Введите сумму расхода и категорию через пробел, например:\n<code>2500 еда</code>"


@router.callback_query(F.data == "menu:budget")
async def cb_open_budget(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("💰 Бюджет карманных денег. Выберите действие:", reply_markup=budget_menu())
    await callback.answer()


@router.callback_query(F.data == "budget:income")
async def cb_budget_income(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BudgetStates.waiting_for_income)
    await callback.message.edit_text(INCOME_PROMPT, reply_markup=back_to_menu())
    await callback.answer()


@router.callback_query(F.data == "budget:expense")
async def cb_budget_expense(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BudgetStates.waiting_for_expense)
    await callback.message.edit_text(EXPENSE_PROMPT, reply_markup=back_to_menu())
    await callback.answer()


def _parse_amount_category(text: str, default_category: str) -> tuple[float, str] | None:
    parts = text.strip().split(maxsplit=1)
    if not parts:
        return None
    try:
        amount = float(parts[0].replace(",", "."))
    except ValueError:
        return None
    if amount <= 0:
        return None
    category = parts[1].strip() if len(parts) > 1 else default_category
    return amount, category


@router.message(BudgetStates.waiting_for_income)
async def handle_income_text(message: Message, state: FSMContext, config: Config) -> None:
    parsed = _parse_amount_category(message.text or "", "доход")
    if parsed is None:
        await message.answer("Не получилось распознать сумму. " + INCOME_PROMPT, reply_markup=back_to_menu())
        return
    amount, category = parsed
    await add_transaction(config.db_path, message.from_user.id, "income", category, amount)
    await message.answer(f"✅ Записал доход: {amount:,.0f} ({category})".replace(",", " "), reply_markup=budget_menu())
    await state.clear()


@router.message(BudgetStates.waiting_for_expense)
async def handle_expense_text(message: Message, state: FSMContext, config: Config) -> None:
    parsed = _parse_amount_category(message.text or "", "прочее")
    if parsed is None:
        await message.answer("Не получилось распознать сумму. " + EXPENSE_PROMPT, reply_markup=back_to_menu())
        return
    amount, category = parsed
    await add_transaction(config.db_path, message.from_user.id, "expense", category, amount)
    await message.answer(f"✅ Записал расход: {amount:,.0f} ({category})".replace(",", " "), reply_markup=budget_menu())
    await state.clear()


@router.callback_query(F.data == "budget:balance")
async def cb_budget_balance(callback: CallbackQuery, config: Config) -> None:
    summary = await get_balance_summary(config.db_path, callback.from_user.id)
    lines = [
        "📊 <b>Ваш баланс</b>",
        f"Доходы: {summary['income']:,.0f}".replace(",", " "),
        f"Расходы: {summary['expense']:,.0f}".replace(",", " "),
        f"Итого: {summary['balance']:,.0f}".replace(",", " "),
    ]
    if summary["top_expenses"]:
        lines.append("\nТоп категорий расходов:")
        for category, amount in summary["top_expenses"]:
            lines.append(f"• {category}: {amount:,.0f}".replace(",", " "))
    await callback.message.edit_text("\n".join(lines), reply_markup=budget_menu())
    await callback.answer()
