from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.market_data import CATEGORY_TITLES, INSTRUMENTS, tickers_by_category
from bot.services.portfolio import RISK_QUESTIONS


def main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🛡 Проверка на мошенничество", callback_data="menu:antifraud")
    builder.button(text="💰 Бюджет", callback_data="menu:budget")
    builder.button(text="📈 Инвест-симулятор", callback_data="menu:invest")
    builder.adjust(1)
    return builder.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Главное меню", callback_data="menu:root")
    return builder.as_markup()


def budget_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Доход", callback_data="budget:income")
    builder.button(text="➖ Расход", callback_data="budget:expense")
    builder.button(text="📊 Баланс", callback_data="budget:balance")
    builder.button(text="⬅️ Главное меню", callback_data="menu:root")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def invest_menu(has_portfolio: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_portfolio:
        builder.button(text="📊 Мой портфель", callback_data="invest:portfolio")
        builder.button(text="🔄 Пройти квиз заново", callback_data="invest:quiz")
    else:
        builder.button(text="📝 Пройти риск-квиз", callback_data="invest:quiz")
    builder.button(text="📉 Рынки", callback_data="invest:markets")
    builder.button(text="⬅️ Главное меню", callback_data="menu:root")
    builder.adjust(1)
    return builder.as_markup()


def risk_quiz_question(question_index: int) -> InlineKeyboardMarkup:
    question = RISK_QUESTIONS[question_index]
    builder = InlineKeyboardBuilder()
    for label, value in question["options"]:
        builder.button(text=label, callback_data=f"quiz:{question_index}:{value}")
    builder.adjust(1)
    return builder.as_markup()


def markets_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category, title in CATEGORY_TITLES.items():
        builder.button(text=title, callback_data=f"invest:markets:{category}")
    builder.button(text="⬅️ Назад", callback_data="menu:invest")
    builder.adjust(1)
    return builder.as_markup()


def instrument_list(category: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ticker in tickers_by_category(category):
        builder.button(text=f"{ticker} — {INSTRUMENTS[ticker]['name']}", callback_data=f"invest:instrument:{ticker}")
    builder.button(text="⬅️ Назад", callback_data="invest:markets")
    builder.adjust(1)
    return builder.as_markup()


def instrument_card(ticker: str, has_holding: bool) -> InlineKeyboardMarkup:
    category = INSTRUMENTS[ticker]["category"]
    builder = InlineKeyboardBuilder()
    builder.button(text="💵 Купить", callback_data=f"invest:buy:{ticker}")
    if has_holding:
        builder.button(text="💰 Продать", callback_data=f"invest:sell:{ticker}")
    builder.button(text="⬅️ К списку", callback_data=f"invest:markets:{category}")
    builder.adjust(1)
    return builder.as_markup()
