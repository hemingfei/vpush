"""手机 APP 键盘遮挡表单（登录页只能盲输）静态回归。

壳（mobile/）targetSdk 35 强制 edge-to-edge 后，manifest 的 windowSoftInputMode
adjustResize 对 IME 失效——窗口不随键盘收缩、键盘纯悬浮，WebView 不知道键盘存在，
登录/注册等表单聚焦时输入框被键盘盖住只能盲输。修复是跨两端接线：
MainActivity 在 SDK≥35 分支把 ime inset 作为 WebView 底部 margin，视口随键盘收窄，
浏览器自动把聚焦输入框滚到键盘上方（Android 15 以下仍由 adjustResize 原生缩窗）；
前端 viewport meta 加 interactive-widget=resizes-content（手机浏览器直接访问同享），
矮视口媒体查询收起品牌介绍、认证页贴顶，登录卡片完整留在键盘上方。
"""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
STATIC = ROOT / "app" / "static"
INDEX_HTML = (STATIC / "index.html").read_text()
STYLE_CSS = (STATIC / "style.css").read_text()
MAIN_ACTIVITY = (ROOT / "mobile" / "android" / "app" / "src" / "main" / "java"
                 / "com" / "icekale" / "vpush" / "MainActivity.java").read_text()
MANIFEST = (ROOT / "mobile" / "android" / "app" / "src" / "main"
            / "AndroidManifest.xml").read_text()


def _balanced_block(text: str, marker: str) -> str:
    """取 marker 之后第一个配平大括号块（含两端大括号），供嵌套 @media 取整块。"""
    start = text.index("{", text.index(marker))
    depth, i = 1, start + 1
    while depth:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return text[start:i]


def test_manifest_declares_adjust_resize():
    """Android 15 以下无 edge-to-edge，靠 adjustResize 原生缩窗把视口让给键盘；
    不声明时系统可自选 adjustPan——整窗平移，输入框仍可能停在键盘下面。"""
    m = re.search(r"<activity\b[^>]*android:name=\"\.MainActivity\"", MANIFEST, re.S)
    assert m, "未找到 MainActivity 声明"
    assert "android:windowSoftInputMode=\"adjustResize\"" in m.group(0)


def test_main_activity_applies_ime_inset_as_webview_bottom_margin():
    """edge-to-edge 下 adjustResize 对 IME 失效，SDK≥35 分支必须把 ime inset 写进
    WebView 底部 margin；收起时 inset 为 0 即还原，且值不变不触发 setLayoutParams。"""
    assert "WindowInsetsCompat.Type.ime()" in MAIN_ACTIVITY
    assert "MarginLayoutParams" in MAIN_ACTIVITY and "bottomMargin" in MAIN_ACTIVITY
    assert re.search(r"bottomMargin\s*!=\s*ime\.bottom", MAIN_ACTIVITY)
    assert "setLayoutParams" in MAIN_ACTIVITY
    # ime inset 与系统栏共用一个监听器（Android 15+ 唯一入口），不得分开挂两个
    assert MAIN_ACTIVITY.index("WindowInsetsCompat.Type.ime()") > MAIN_ACTIVITY.index(
        "WindowInsetsCompat.Type.statusBars()")


def test_viewport_meta_resizes_content_for_keyboard():
    """手机浏览器（非壳）兜底：interactive-widget=resizes-content 让 Chrome 弹键盘时
    收缩布局视口，聚焦输入框才会被自动滚到键盘上方（WebView 内由原生 margin 负责）。"""
    vp = re.search(r"<meta name=\"viewport\" content=\"([^\"]+)\"", INDEX_HTML)
    assert vp, "未找到 viewport meta"
    assert "interactive-widget=resizes-content" in vp.group(1)


def test_short_viewport_hides_login_brand():
    """max-height 命中（键盘弹出/矮视口）时收起品牌介绍、认证页贴顶，
    登录卡片连同聚焦输入框完整留在键盘上方。"""
    block = _balanced_block(STYLE_CSS, "@media (max-height: 620px)")
    compact = re.sub(r"\s+", "", block)
    assert ".login-brand{display:none;}" in compact
    assert "align-items:flex-start" in compact
    # 块内 padding-bottom 是长手写属性，须排在 900px 块的 padding 简写之后才能覆盖
    assert STYLE_CSS.index("padding: 56px 16px 32px") < STYLE_CSS.index(
        "@media (max-height: 620px)")
