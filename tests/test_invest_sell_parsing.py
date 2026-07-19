from bot.handlers.invest import _parse_sell_amount


def test_all_keyword_returns_held_shares():
    assert _parse_sell_amount("всё", 3.5) == 3.5
    assert _parse_sell_amount("все", 3.5) == 3.5
    assert _parse_sell_amount("ALL", 3.5) == 3.5


def test_parses_partial_amount():
    assert _parse_sell_amount("1.5", 3.5) == 1.5


def test_accepts_comma_decimal():
    assert _parse_sell_amount("1,5", 3.5) == 1.5


def test_rejects_amount_over_held():
    assert _parse_sell_amount("10", 3.5) is None


def test_rejects_zero_or_negative():
    assert _parse_sell_amount("0", 3.5) is None
    assert _parse_sell_amount("-1", 3.5) is None


def test_rejects_garbage():
    assert _parse_sell_amount("abc", 3.5) is None


def test_accepts_amount_equal_to_held():
    assert _parse_sell_amount("3.5", 3.5) == 3.5
