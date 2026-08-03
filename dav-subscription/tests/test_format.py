from app.fetchers.base import Post
from app.notifiers.feishu import build_feishu_card
from app.notifiers.telegram import build_telegram_text


def make_post() -> Post:
    return Post(
        platform="xueqiu",
        kol_id=1,
        kol_name="张三",
        external_id="1",
        title="看多",
        content="今天 <b>大涨</b>",
        url="https://xueqiu.com/1",
        published_at="2026-08-04",
    )


def test_feishu_card_contains_author_and_url():
    card = build_feishu_card(make_post())
    assert card["msg_type"] == "interactive"
    assert "张三" in card["card"]["header"]["title"]["content"]
    button = card["card"]["elements"][-1]["actions"][0]
    assert button["url"] == "https://xueqiu.com/1"


def test_telegram_text_escapes_html():
    text = build_telegram_text(make_post())
    assert "<b>看多</b>" in text
    assert "&lt;b&gt;大涨&lt;/b&gt;" in text
    assert 'href="https://xueqiu.com/1"' in text
