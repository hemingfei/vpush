"""待审标签大众评审前端静态回归（照 test_frontend_holdings.py 体例）。

覆盖：待审徽章可点开审核弹窗（带 review id）、弹窗投票接线、INLINE_HANDLERS
契约、管理后台大众评审配置表单及其跨文件接线（kol.js → app.js 懒加载解构）。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
KOL_JS = (STATIC / "views" / "admin" / "kol.js").read_text(encoding="utf-8")
STYLE_CSS = (STATIC / "style.css").read_text(encoding="utf-8")


def _fn_body(name: str, src: str = APP_JS) -> str:
    m = re.search(rf"async\s+function\s+{name}\b|function\s+{name}\b", src)
    assert m, f"未找到函数 {name}"
    start = src.index("{", src.index("(", m.end()))
    depth, i = 1, start + 1
    while depth:
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
        i += 1
    return src[start:i]


def test_pending_chips_open_vote_modal_when_review_id_present():
    chips = _fn_body("renderPostTagChips")
    # 有审核 id：button 形态可点开弹窗；旧缓存无 id：保持只读 span
    assert "tag-review-open" in chips
    assert "data-review-id" in chips and "openTagVoteModal(" in chips
    assert "if (rid)" in chips
    raw = _fn_body("mxRawTagsHtml")
    assert "tag-review-open" in raw and "openTagVoteModal(" in raw


def test_vote_modal_wiring_and_inline_handlers():
    for name in ("openTagVoteModal", "closeTagVoteModal", "submitTagVote", "refreshTagVoteChips"):
        assert _fn_body(name), name
    inline = APP_JS[APP_JS.index("const INLINE_HANDLERS"):]
    for name in ("openTagVoteModal", "closeTagVoteModal", "submitTagVote"):
        assert re.search(rf"^\s+{name},$", inline, re.M), name
    body = _fn_body("openTagVoteModal")
    assert "/api/tag-reviews/" in body
    submit = _fn_body("submitTagVote")
    assert "/vote" in submit and "refreshTagVoteChips(" in submit
    # 弹窗复用统一背景滚动锁，关闭时解锁
    assert "lockBodyScroll()" in body and "unlockBodyScroll()" in _fn_body("closeTagVoteModal")


def test_vote_modal_renders_progress_and_rules():
    paint = _fn_body("paintTagVoteModal")
    assert "can_vote" in paint and "my_vote" in paint
    assert "unanimous_n" in paint and "max_voters" in paint  # 裁决规则提示
    assert "tag-vote-progress" in paint and "tag-vote-actions" in paint
    assert "管理员直判" in paint  # 管理员直判提示
    # 裁决后就地更新徽章：禁用点击并改角标文案
    refresh = _fn_body("refreshTagVoteChips")
    assert "disabled = true" in refresh and "已通过" in refresh and "已拒绝" in refresh


def test_admin_vote_config_form_and_wiring():
    panel = _fn_body("adminMxTagPanel", KOL_JS)
    assert "tag-review-public" in panel
    assert "tag-review-unanimous" in panel and "tag-review-max" in panel
    assert "adminSaveTagReviewConfig()" in panel
    save = _fn_body("adminSaveTagReviewConfig", KOL_JS)
    assert "/api/admin/tag-review/config" in save and "method: \"PUT\"" in save
    # kol.js 工厂导出 → app.js 懒加载解构 → INLINE_HANDLERS（window 挂载）
    assert re.search(r"^\s+adminSaveTagReviewConfig,$", KOL_JS, re.M)
    lazy = APP_JS[APP_JS.index("let kolView, loadAdminKols"):APP_JS.index("// admin 视图懒加载：infra")]
    assert "adminSaveTagReviewConfig" in lazy
    destructure = APP_JS[APP_JS.index("} = (kolView = modKol.createAdminKolsView(") - 2500:
                         APP_JS.index("} = (kolView = modKol.createAdminKolsView(")]
    assert "adminSaveTagReviewConfig," in destructure
    inline = APP_JS[APP_JS.index("const INLINE_HANDLERS"):]
    assert re.search(r"^\s+adminSaveTagReviewConfig,$", inline, re.M)
    # 装载标签 tab 时并行拉取配置
    load = _fn_body("loadAdminTagsTab", KOL_JS)
    assert "/api/admin/tag-review/config" in load


def test_vote_styles_present():
    assert ".tag-vote-card" in STYLE_CSS
    assert ".tag-review-open" in STYLE_CSS  # 可点 chip 指针态
    assert ".tag-review-vote-config" in STYLE_CSS
    assert ".tag-pending-badge.is-approved" in STYLE_CSS
