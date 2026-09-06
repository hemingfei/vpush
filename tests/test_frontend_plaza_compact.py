"""订阅广场大V卡片手机端紧凑化 静态回归。

手机上一屏此前只能看到 2~3 张大V卡片：卡片内边距 16px、头像 52px、
外部 ID 独占一行。现收紧为 10/12px 内边距、40px 头像，外部 ID 并入
平台标签行；操作按钮触控目标仍保 44px。锁定这些约定不被无声回退。
"""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
APP_JS = (ROOT / "app" / "static" / "app.js").read_text()
STYLE_CSS = (ROOT / "app" / "static" / "style.css").read_text()


def _fn_body(name: str) -> str:
    m = re.search(rf"function {name}\([^)]*\) {{", APP_JS)
    assert m, f"app.js 未定义 {name}"
    start = APP_JS.index("{", m.end() - 1)
    depth, i = 1, start + 1
    while depth:
        if APP_JS[i] == "{":
            depth += 1
        elif APP_JS[i] == "}":
            depth -= 1
        i += 1
    return APP_JS[start:i]


def _media_blocks(prelude: str) -> list[str]:
    blocks = []
    for m in re.finditer(re.escape(prelude), STYLE_CSS):
        start = STYLE_CSS.index("{", m.end())
        depth, i = 1, start + 1
        while depth:
            if STYLE_CSS[i] == "{":
                depth += 1
            elif STYLE_CSS[i] == "}":
                depth -= 1
            i += 1
        blocks.append(STYLE_CSS[start:i])
    return blocks


def test_kol_card_external_id_inline_with_tags():
    """外部 ID 挂进 .kol-card-meta 标签行，不再独占 <div class="desc"> 一行。"""
    card = _fn_body("kolCard")
    assert '<span class="ext-id">外部 ID：' in card
    assert '<div class="desc">外部 ID' not in card
    # ext-id 经 tags 数组进入 meta 行模板渲染
    assert '<div class="kol-card-meta">${tags.join("")}</div>' in card
    # 停用标记跟随外部 ID 一并移入标签行
    assert card.index('class="ext-id"') < card.index("已停用")


def test_ext_id_style_lives_in_meta_row():
    rule = re.search(r"^\.kol-card-meta \.ext-id\s*\{([^}]*)\}", STYLE_CSS, re.M)
    assert rule, "缺少 .kol-card-meta .ext-id 样式"
    assert "var(--text-xs)" in rule.group(1)
    assert "var(--color-text-muted)" in rule.group(1)
    assert ".kol-card-info .desc" not in STYLE_CSS  # 旧规则随结构一并移除


def test_mobile_media_compacts_kol_cards():
    """≤768px：网格/卡片间距、内边距、头像、分组头收紧；按钮保持 44px 触控。"""
    compact = ".kol-card { gap: 8px; padding: 10px 12px; }"
    blocks = [b for b in _media_blocks("@media (max-width: 768px)") if compact in b]
    assert len(blocks) == 1, "移动端媒体查询应恰好包含一处 .kol-card 紧凑规则"
    block = blocks[0]
    assert ".kol-grid { gap: 10px; }" in block
    assert ".kol-card-head { gap: 10px; }" in block
    assert ".kol-card .kol-avatar { width: 40px; height: 40px; font-size: 17px; }" in block
    assert ".kol-card-meta { margin-top: 2px; gap: 4px 6px; }" in block
    assert ".kol-card-info .tag { padding: 1px 8px; }" in block
    assert ".group-head { margin: 12px 2px 6px; padding: 6px 10px; }" in block
    assert ".kol-card .btn-sub, .kol-card .fav-btn, .kol-card .btn-sm.danger { min-height: 44px; }" in block


def test_desktop_base_keeps_name_wrap_and_flex_meta():
    """基础规则（桌面）不动：名字可换行不裁剪，meta 行仍是可换行 flex。"""
    name = re.search(r"^\.kol-card-info \.name\s*\{([^}]*)\}", STYLE_CSS, re.M)
    meta = re.search(r"^\.kol-card-meta\s*\{([^}]*)\}", STYLE_CSS, re.M)
    assert name and "overflow-wrap: anywhere" in name.group(1)
    assert meta and "flex-wrap: wrap" in meta.group(1)
