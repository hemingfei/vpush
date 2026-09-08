from app.zh_simp import to_simplified


def test_to_simplified_t2s_identity_and_empty():
    assert to_simplified("這個帳號在臺灣發了繁體中文") == "这个账号在台湾发了繁体中文"
    assert to_simplified("已经是简体 ETF") == "已经是简体 ETF"
    assert to_simplified("") == ""
    assert to_simplified(None) == ""
