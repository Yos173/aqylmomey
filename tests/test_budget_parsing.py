from bot.handlers.budget import _parse_amount_category


def test_parses_amount_and_category():
    assert _parse_amount_category("2500 еда", "прочее") == (2500.0, "еда")


def test_uses_default_category_when_omitted():
    assert _parse_amount_category("50000", "доход") == (50000.0, "доход")


def test_accepts_comma_as_decimal_separator():
    assert _parse_amount_category("99,50 транспорт", "прочее") == (99.5, "транспорт")


def test_category_can_contain_spaces():
    result = _parse_amount_category("1000 такси домой", "прочее")
    assert result == (1000.0, "такси домой")


def test_rejects_non_numeric_amount():
    assert _parse_amount_category("абв еда", "прочее") is None


def test_rejects_zero_or_negative_amount():
    assert _parse_amount_category("0 еда", "прочее") is None
    assert _parse_amount_category("-100 еда", "прочее") is None


def test_rejects_empty_input():
    assert _parse_amount_category("", "прочее") is None
    assert _parse_amount_category("   ", "прочее") is None
