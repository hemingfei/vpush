"""全市场正式简称：3 字及以上参与纯文字打标，两字名只认常用表。"""
from app.stock_universe import (
    UNIVERSE_MIN_LEN,
    aliases_for_tagging,
    bundled_plain_names,
    names_for_plain_text_tagging,
    universe_meta,
)
from app.tagging import stock_tag_posts
from tests.test_tagging import make_post


def test_bundled_universe_is_mostly_long_official_names():
    names = bundled_plain_names()
    meta = universe_meta()
    assert meta["count"] == len(names)
    assert meta["count"] > 4000
    assert all(len(n) >= UNIVERSE_MIN_LEN for n in names)
    assert "宁德时代" in names
    assert "五粮液" in names
    assert "柳工" not in names


def test_plain_text_uses_universe_and_keeps_curated_short_names():
    names = names_for_plain_text_tagging(["茅台"], excluded=None, universe=["浦发银行", "柳工"])
    assert "茅台" in names
    assert "浦发银行" in names
    assert "柳工" not in names


def test_plain_text_respects_admin_exclusions():
    names = names_for_plain_text_tagging(
        ["宁德时代", "茅台"],
        excluded=["宁德时代", "浦发银行"],
        universe=["浦发银行", "五粮液"],
    )
    assert "宁德时代" not in names
    assert "浦发银行" not in names
    assert "茅台" in names
    assert "五粮液" in names


def test_stock_tag_posts_hits_universe_name():
    post = make_post(content="下午看了眼浦发银行的走势")
    names = names_for_plain_text_tagging([], universe=["浦发银行"])
    assert stock_tag_posts([post], names)[0] == ["浦发银行"]


def test_aliases_for_tagging_drop_excluded_officials():
    kept = aliases_for_tagging(
        [
            {"alias": "宁王", "stock": "宁德时代"},
            {"alias": "岸科技", "stock": "千岸科技"},
        ],
        excluded=["千岸科技"],
    )
    assert kept == [{"alias": "宁王", "stock": "宁德时代"}]


def test_stock_tag_posts_skips_excluded_universe_name():
    post = make_post(content="下午看了眼浦发银行的走势")
    names = names_for_plain_text_tagging([], excluded=["浦发银行"], universe=["浦发银行"])
    assert stock_tag_posts([post], names)[0] == []
