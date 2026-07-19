import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from bot.webapp.auth import InitDataError, parse_and_validate_init_data

BOT_TOKEN = "123456:test-token"


def _build_init_data(user: dict, bot_token: str = BOT_TOKEN, auth_date: int | None = None) -> str:
    fields = {
        "user": json.dumps(user, separators=(",", ":")),
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAEfake",
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    fields["hash"] = signature
    return urlencode(fields)


def test_valid_init_data_returns_user():
    init_data = _build_init_data({"id": 42, "username": "alice"})
    user = parse_and_validate_init_data(init_data, BOT_TOKEN)
    assert user["id"] == 42
    assert user["username"] == "alice"


def test_empty_init_data_rejected():
    with pytest.raises(InitDataError):
        parse_and_validate_init_data("", BOT_TOKEN)


def test_missing_hash_rejected():
    with pytest.raises(InitDataError):
        parse_and_validate_init_data("user=%7B%22id%22%3A1%7D&auth_date=123", BOT_TOKEN)


def test_tampered_payload_rejected():
    init_data = _build_init_data({"id": 42, "username": "alice"})
    tampered = init_data.replace("alice", "mallory")
    with pytest.raises(InitDataError):
        parse_and_validate_init_data(tampered, BOT_TOKEN)


def test_wrong_bot_token_rejected():
    init_data = _build_init_data({"id": 42, "username": "alice"})
    with pytest.raises(InitDataError):
        parse_and_validate_init_data(init_data, "999999:other-token")


def test_expired_init_data_rejected():
    old_auth_date = int(time.time()) - 999_999
    init_data = _build_init_data({"id": 42, "username": "alice"}, auth_date=old_auth_date)
    with pytest.raises(InitDataError):
        parse_and_validate_init_data(init_data, BOT_TOKEN, max_age_seconds=86400)


def test_expired_init_data_accepted_when_max_age_disabled():
    old_auth_date = int(time.time()) - 999_999
    init_data = _build_init_data({"id": 42, "username": "alice"}, auth_date=old_auth_date)
    user = parse_and_validate_init_data(init_data, BOT_TOKEN, max_age_seconds=0)
    assert user["id"] == 42


def test_missing_user_field_rejected():
    fields = {"auth_date": str(int(time.time()))}
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    with pytest.raises(InitDataError):
        parse_and_validate_init_data(urlencode(fields), BOT_TOKEN)
