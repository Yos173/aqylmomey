from aiogram.fsm.state import State, StatesGroup


class AntifraudStates(StatesGroup):
    waiting_for_text = State()


class BudgetStates(StatesGroup):
    waiting_for_income = State()
    waiting_for_expense = State()


class InvestStates(StatesGroup):
    quiz_in_progress = State()
    waiting_for_buy_amount = State()
    waiting_for_sell_amount = State()
