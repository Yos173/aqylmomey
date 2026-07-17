from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.db import ensure_user
from bot.keyboards import main_menu

router = Router(name="start")

WELCOME_TEXT = (
    "👋 Привет! Это <b>AqylMoney</b> — бот по финансовой грамотности хакатона Tech Vision.\n\n"
    "Что умею:\n"
    "🛡 Проверять сообщения на признаки финансового мошенничества\n"
    "💰 Вести простой бюджет карманных денег\n"
    "📈 Обучающий инвест-симулятор на реальных рыночных данных (деньги виртуальные)\n\n"
    "Выберите раздел:"
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, config: Config) -> None:
    await state.clear()
    await ensure_user(config.db_path, message.from_user.id, message.from_user.username)
    await message.answer(WELCOME_TEXT, reply_markup=main_menu())


@router.callback_query(F.data == "menu:root")
async def cb_root_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Главное меню. Выберите раздел:", reply_markup=main_menu())
    await callback.answer()
