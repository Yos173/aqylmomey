from bot.services.fraud_scoring import score_text, score_to_verdict, template_explanation, rule_labels


def test_clean_message_is_low_risk():
    result = score_text("Привет! Как дела? Встретимся завтра в кафе.")
    assert result.score == 0
    assert result.verdict == "low"
    assert result.triggered_rules == []


def test_unrealistic_return_triggers_rule():
    result = score_text("Инвестируй и получи гарантированный доход 200% годовых!")
    assert "unrealistic_return" in result.triggered_rules
    assert result.score >= 30


def test_sensitive_info_request_triggers_rule():
    result = score_text("Пришлите код из смс и номер карты для подтверждения")
    assert "sensitive_info_request" in result.triggered_rules
    assert result.score >= 35


def test_urgency_pressure_triggers_rule():
    result = score_text("Только сегодня! Успейте купить, осталось 3 места")
    assert "urgency_pressure" in result.triggered_rules


def test_suspicious_link_triggers_rule():
    result = score_text("Перейдите по ссылке bit.ly/abc123")
    assert "suspicious_link" in result.triggered_rules


def test_easy_money_scheme_triggers_rule():
    result = score_text("Лёгкий заработок без вложений, пригласи друга и получи бонус")
    assert "easy_money_scheme" in result.triggered_rules


def test_multiple_signals_stack_score_and_cap_at_100():
    text = (
        "Только сегодня! Гарантированный доход 300% годовых. "
        "Пришлите номер карты и код из смс. Лёгкий заработок без вложений. "
        "Подробности: bit.ly/xyz"
    )
    result = score_text(text)
    assert result.score == 100
    assert result.verdict == "high"
    assert len(result.triggered_rules) >= 4


def test_verdict_thresholds():
    assert score_text("").verdict == "low"

    medium = score_text("Только сегодня! Успейте, осталось 5 мест")
    assert medium.score < 60
    assert medium.verdict in ("low", "medium")

    high = score_text("Гарантированный доход 500% годовых, переведите деньги на карту")
    assert high.score >= 60
    assert high.verdict == "high"


def test_template_explanation_no_signals():
    from bot.services.fraud_scoring import score_text as st

    result = st("Обычное сообщение без подвоха")
    explanation = template_explanation(result)
    assert "Явных признаков" in explanation


def test_template_explanation_lists_labels():
    result = score_text("Гарантированный доход 200% годовых")
    explanation = template_explanation(result)
    labels = rule_labels(result.triggered_rules)
    for label in labels:
        assert label in explanation


def test_kaspi_code_phishing_triggers_sensitive_info_request():
    result = score_text("Пришлите код подтверждения Kaspi, чтобы отменить платёж")
    assert "sensitive_info_request" in result.triggered_rules


def test_kaspi_giveaway_scam_triggers_easy_money_scheme():
    result = score_text("Поздравляем! Вы выиграли в розыгрыше Kaspi, заберите приз")
    assert "easy_money_scheme" in result.triggered_rules


def test_kaspi_phrases_do_not_false_positive_on_unrelated_text():
    result = score_text("Оплатил обед через Kaspi, всё как обычно")
    assert result.triggered_rules == []


def test_score_to_verdict_boundaries():
    assert score_to_verdict(0) == "low"
    assert score_to_verdict(24) == "low"
    assert score_to_verdict(25) == "medium"
    assert score_to_verdict(59) == "medium"
    assert score_to_verdict(60) == "high"
    assert score_to_verdict(100) == "high"
