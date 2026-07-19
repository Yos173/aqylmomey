from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.db import log_fraud_check
from bot.keyboards import back_to_menu
from bot.services.fraud_scoring import VERDICT_TITLES, score_text, template_explanation
from bot.services.llm_client import explain_fraud_signals
from bot.states import AntifraudStates

router = Router(name="antifraud")

PROMPT_TEXT = (
    "Пришлите текстом подозрительное сообщение, объявление или ссылку, которую хотите проверить "
    "(например: 'Инвестируй 10000 тенге и получи 50000 за неделю, только сегодня!')."
)


@router.callback_query(F.data == "menu:antifraud")
async def cb_open_antifraud(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AntifraudStates.waiting_for_text)
    await callback.message.edit_text(PROMPT_TEXT, reply_markup=back_to_menu())
    await callback.answer()


@router.message(AntifraudStates.waiting_for_text)
async def handle_fraud_text(message: Message, state: FSMContext, config: Config) -> None:
    text = message.text or ""
    result = score_text(text)
    await log_fraud_check(config.db_path, message.from_user.id, result.score, result.verdict, result.triggered_rules)

    explanation = await explain_fraud_signals(config.anthropic_api_key, text, result)
    if explanation is None:
        explanation = template_explanation(result)

    reply = (
        f"{VERDICT_TITLES[result.verdict]}\n"
        f"Оценка риска: {result.score}/100\n\n"
        f"{explanation}\n\n"
        "⚠️ Это автоматическая обучающая оценка, а не юридическое заключение. "
        "При сомнениях не переводите деньги и не сообщайте коды из СМС."
    )
    await message.answer(reply, reply_markup=back_to_menu())
    await state.clear()
