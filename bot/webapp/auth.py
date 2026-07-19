import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class InitDataError(Exception):
    """initData отсутствует, повреждён, подделан или устарел."""


def parse_and_validate_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> dict:
    """Проверяет подпись Telegram WebApp initData и возвращает распарсенного пользователя.

    Алгоритм соответствует официальной документации Telegram:
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app
    """
    if not init_data:
        raise InitDataError("initData пустой")

    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError as exc:
        raise InitDataError("не удалось разобрать initData") from exc

    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InitDataError("отсутствует hash")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise InitDataError("недействительная подпись initData")

    auth_date = int(pairs.get("auth_date", "0"))
    if max_age_seconds and (time.time() - auth_date) > max_age_seconds:
        raise InitDataError("initData устарел")

    user_raw = pairs.get("user")
    if not user_raw:
        raise InitDataError("в initData отсутствует пользователь")

    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise InitDataError("не удалось разобрать поле user") from exc

    if "id" not in user:
        raise InitDataError("у пользователя отсутствует id")

    return user
