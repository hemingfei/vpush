from app.tagging import tag_text


def test_tag_text_uses_vocab_and_stock_names():
    tags = tag_text(
        "宁德时代产业链点评",
        "新能源车需求回暖，宁德时代排产上修。",
        tag_rules=[{"tag": "新能源", "keywords": ["新能源车", "排产"]}],
        stock_names=["宁德时代", "贵州茅台"],
        aliases=[{"alias": "宁王", "stock": "宁德时代"}],
    )
    assert "新能源" in tags
    assert "宁德时代" in tags
    assert tags.count("宁德时代") == 1


def test_tag_text_empty_when_no_hit():
    assert tag_text("无标题", "无关正文", tag_rules=[], stock_names=[], aliases=[]) == []
