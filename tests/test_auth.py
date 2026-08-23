import pytest

from app.api import account_origin
from app.auth import USERNAME_CHARSET_MSG, is_valid_username, validate_username


@pytest.mark.parametrize(
    "name",
    ["Yansy102", "user_01", "user-01", "abcdef", "张三李四王五", "李四abcd"],
)
def test_validate_username_accepts_reasonable_names(name):
    assert validate_username(f"  {name}  ") == name


@pytest.mark.parametrize(
    "name, message",
    [
        ("ab", "用户名至少6位"),
        ("abcde", "用户名至少6位"),
        ("a" * 31, "用户名最长30位"),
        ("ag's trend", USERNAME_CHARSET_MSG),
        ("hello world", USERNAME_CHARSET_MSG),
        ("123456", USERNAME_CHARSET_MSG),
        ("_abcdef", USERNAME_CHARSET_MSG),
        ("-abcdef", USERNAME_CHARSET_MSG),
        ("hello!", USERNAME_CHARSET_MSG),
        ("<script>", USERNAME_CHARSET_MSG),
        ("emoji😀name", USERNAME_CHARSET_MSG),
    ],
)
def test_validate_username_rejects_unreasonable_names(name, message):
    with pytest.raises(ValueError, match=message):
        validate_username(name)


def test_is_valid_username_flags_dirty_login_names():
    assert is_valid_username("Yansy102") is True
    assert is_valid_username("ag's trend") is False
    assert is_valid_username("admin") is False


@pytest.mark.parametrize(
    "user, invite, origin",
    [
        ({"wechat_openid": "ox1"}, {"code": "ABCD1234"}, "invite"),
        ({"telegram_chat_id": "1", "password_hash": "x"}, {"code": "ABCD1234"}, "invite"),
        ({"wechat_openid": "ox1"}, None, "wechat"),
        ({"wechat_openid": "ox1", "password_hash": "x"}, None, "wechat"),
        ({"telegram_chat_id": "1"}, None, "telegram"),
        ({"feishu_open_id": "ou_1"}, None, "feishu"),
        ({"feishu_chat_id": "oc_1"}, None, "feishu"),
        ({"telegram_chat_id": "1", "password_hash": "x"}, None, "web"),
        ({"feishu_open_id": "ou_1", "password_hash": "x"}, None, "web"),
        ({"password_hash": "x"}, None, "web"),
    ],
)
def test_account_origin(user, invite, origin):
    assert account_origin(user, invite) == origin
