import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot.services.fraud_scoring import score_text
from bot.services.llm_client import assess_fraud_risk, ask_assistant


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_response(text: str, stop_reason: str = "end_turn"):
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)])


def _mock_client(response):
    client = AsyncMock()
    client.messages.create = AsyncMock(return_value=response)
    return client


@pytest.mark.anyio
async def test_assess_fraud_risk_parses_structured_output():
    payload = json.dumps({"score": 72, "red_flags": ["давление на жертву"], "explanation": "Похоже на схему."})
    client = _mock_client(_make_response(payload))

    with patch("bot.services.llm_client.AsyncAnthropic", return_value=client):
        result = await assess_fraud_risk("fake-key", "some text", score_text("some text"))

    assert result == {"score": 72, "red_flags": ["давление на жертву"], "explanation": "Похоже на схему."}


@pytest.mark.anyio
async def test_assess_fraud_risk_clamps_score_to_0_100():
    payload = json.dumps({"score": 150, "red_flags": [], "explanation": "explanation"})
    client = _mock_client(_make_response(payload))

    with patch("bot.services.llm_client.AsyncAnthropic", return_value=client):
        result = await assess_fraud_risk("fake-key", "text", score_text("text"))

    assert result["score"] == 100


@pytest.mark.anyio
async def test_assess_fraud_risk_clamps_negative_score():
    payload = json.dumps({"score": -10, "red_flags": [], "explanation": "explanation"})
    client = _mock_client(_make_response(payload))

    with patch("bot.services.llm_client.AsyncAnthropic", return_value=client):
        result = await assess_fraud_risk("fake-key", "text", score_text("text"))

    assert result["score"] == 0


@pytest.mark.anyio
async def test_assess_fraud_risk_returns_none_without_key():
    assert await assess_fraud_risk(None, "text", score_text("text")) is None


@pytest.mark.anyio
async def test_assess_fraud_risk_returns_none_on_refusal():
    client = _mock_client(_make_response("{}", stop_reason="refusal"))
    with patch("bot.services.llm_client.AsyncAnthropic", return_value=client):
        result = await assess_fraud_risk("fake-key", "text", score_text("text"))
    assert result is None


@pytest.mark.anyio
async def test_assess_fraud_risk_returns_none_on_client_exception():
    client = AsyncMock()
    client.messages.create = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("bot.services.llm_client.AsyncAnthropic", return_value=client):
        result = await assess_fraud_risk("fake-key", "text", score_text("text"))
    assert result is None


@pytest.mark.anyio
async def test_assess_fraud_risk_returns_none_on_malformed_json():
    client = _mock_client(_make_response("not valid json"))
    with patch("bot.services.llm_client.AsyncAnthropic", return_value=client):
        result = await assess_fraud_risk("fake-key", "text", score_text("text"))
    assert result is None


@pytest.mark.anyio
async def test_assess_fraud_risk_returns_none_when_required_fields_missing():
    payload = json.dumps({"red_flags": []})  # no score / explanation
    client = _mock_client(_make_response(payload))
    with patch("bot.services.llm_client.AsyncAnthropic", return_value=client):
        result = await assess_fraud_risk("fake-key", "text", score_text("text"))
    assert result is None


@pytest.mark.anyio
async def test_ask_assistant_returns_answer_text():
    client = _mock_client(_make_response("Не переводите деньги незнакомцам."))
    with patch("bot.services.llm_client.AsyncAnthropic", return_value=client):
        answer = await ask_assistant("fake-key", "Стоит ли доверять таким предложениям?", ["urgency_pressure"])
    assert answer == "Не переводите деньги незнакомцам."


@pytest.mark.anyio
async def test_ask_assistant_returns_none_without_key():
    assert await ask_assistant(None, "вопрос", []) is None


@pytest.mark.anyio
async def test_ask_assistant_returns_none_on_refusal():
    client = _mock_client(_make_response("", stop_reason="refusal"))
    with patch("bot.services.llm_client.AsyncAnthropic", return_value=client):
        answer = await ask_assistant("fake-key", "вопрос", [])
    assert answer is None
