"""手机 APP 返回键接管 + 智囊团抽屉状态栏安全区 静态回归。

壳是 Capacitor（mobile/），加载自托管服务器前端；返回键逻辑跨原生/web 两端：
MainActivity 用 OnBackPressedCallback 接管 → 询问页面 window.__VPUSH_BACK__ →
页面没消费则退 WebView 历史 → 到根弹退出确认框。此处锁定两端的接线不被无声破坏。
"""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
STATIC = ROOT / "app" / "static"
APP_JS = (STATIC / "app.js").read_text()
MX_CSS = (STATIC / "mx-views.css").read_text()
MAIN_ACTIVITY = (ROOT / "mobile" / "android" / "app" / "src" / "main" / "java"
                 / "com" / "icekale" / "vpush" / "MainActivity.java").read_text()
STRINGS = (ROOT / "mobile" / "android" / "app" / "src" / "main" / "res"
           / "values" / "strings.xml").read_text()


def _back_hook_body() -> str:
    m = re.search(r"window\.__VPUSH_BACK__\s*=\s*function\s*\([^)]*\)\s*{", APP_JS)
    assert m, "app.js 未定义 window.__VPUSH_BACK__ 钩子"
    start = APP_JS.index("{", m.end() - 1)
    depth, i = 1, start + 1
    while depth:
        if APP_JS[i] == "{":
            depth += 1
        elif APP_JS[i] == "}":
            depth -= 1
        i += 1
    return APP_JS[start:i]


def test_back_hook_closes_overlays_then_navigates_back():
    """返回键消费次序：灯箱 → 通用弹窗 → 智囊团抽屉 → 子页返回 → history，最后交还原生。"""
    body = _back_hook_body()
    assert ".lightbox:not(.closing)" in body and "closeLightbox()" in body
    assert ".modal-mask" in body and "[data-close]" in body  # 优先点弹窗自己的取消键
    assert ".mxv-drawer" in body and "mxvCloseDrawer()" in body
    assert "state.pageBackRoute" in body and "go(state.pageBackRoute)" in body
    assert "history.length > 1" in body and "history.back()" in body
    assert "return false" in body  # 根视图不消费，原生弹退出确认
    # 次序固定：遮罩在前、页面返回在后
    assert body.index(".mxv-drawer") < body.index("state.pageBackRoute")


def test_drawer_clears_status_bar_safe_area():
    """抽屉顶部腾出状态栏高度（--safe-top 由 style.css env() 与安卓注入共同供给），
    手机全屏抽屉的右上角 ✕ 不再与状态栏重合。"""
    start = MX_CSS.index(".mxv-drawer{")
    block = MX_CSS[start:MX_CSS.index("}", start)]
    assert "padding-top:calc(16px+var(--safe-top,0px))" in block.replace(" ", "")


def test_main_activity_intercepts_back_with_page_probe_and_exit_dialog():
    """原生侧：OnBackPressedCallback 接管 → 询问 __VPUSH_BACK__ → canGoBack → 确认退出。"""
    assert "OnBackPressedCallback" in MAIN_ACTIVITY and "handleOnBackPressed" in MAIN_ACTIVITY
    assert "window.__VPUSH_BACK__" in MAIN_ACTIVITY  # 先问页面要不要自己消费
    assert "canGoBack()" in MAIN_ACTIVITY and "goBack()" in MAIN_ACTIVITY  # 页面没消费退历史
    assert "AlertDialog" in MAIN_ACTIVITY  # 到根弹退出确认，而非直接退出
    assert '("true".equals(value))' in MAIN_ACTIVITY  # 页面消费了就不做默认行为
    for name in ("exit_confirm_message", "exit_cancel", "exit_ok"):
        assert f'name="{name}"' in STRINGS, name
