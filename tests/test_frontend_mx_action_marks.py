"""大V消息操作标注前端注册静态回归（弹窗/卡片角标/时间线徽章/管理面板）。"""
import re
from pathlib import Path

STATIC = Path(__file__).parent.parent / "app" / "static"
APP_JS = (STATIC / "app.js").read_text()
MXC_JS = (STATIC / "views" / "mx-kol-holdings.js").read_text()
ADMIN_KOL_JS = (STATIC / "views" / "admin" / "kol.js").read_text()
STYLE_CSS = (STATIC / "style.css").read_text()
MXC_CSS = (STATIC / "mx-kol-holdings.css").read_text()

INLINE_HANDLERS = APP_JS[APP_JS.index("const INLINE_HANDLERS"):]


def test_action_mark_modal_handlers_registered():
    """标注弹窗的 6 个内联 handler 必须进 INLINE_HANDLERS（check 脚本同口径）。"""
    for fn in ("openActionMarkModal", "closeActionMarkModal", "actionMarkPick",
               "actionMarkFillTarget", "submitActionMark", "deleteActionMark",
               "refreshActionMarkChips"):
        assert f"function {fn}" in APP_JS, f"缺函数 {fn}"
        assert re.search(rf"^\s+{fn},$", INLINE_HANDLERS, re.M), f"{fn} 未注册进 INLINE_HANDLERS"


def test_action_mark_modal_calls_api_contract():
    """弹窗读写走 /api/posts/{id}/action-mark，POST body 携带 target_name+action。"""
    assert "await api(`/api/posts/${postId}/action-mark`)" in APP_JS
    assert 'JSON.stringify({ target_name: target, action })' in APP_JS
    assert 'method: "DELETE"' in APP_JS
    # 弹窗 mask 挂 id 供关闭/重绘定位；表单输入元素 id 供提交读取
    assert 'mask.id = "action-mark-mask"' in APP_JS
    assert 'id="am-target"' in APP_JS
    # 生效提示语按角色区分
    assert "直判生效" in APP_JS
    assert "等待其他用户确认" in APP_JS
    # DELETE 逐条撤销：target_name 进查询串（null = 全撤）
    assert 'params.set("target_name", targetName)' in APP_JS


def test_action_mark_modal_shows_auto_and_multi_marks():
    """弹窗展示自动标注（posts.tags）与多条人工标注，支持逐条撤销。"""
    assert ">自动标注" in APP_JS  # 自动标注区标题
    assert "data.auto_tags" in APP_JS and "data.llm_tagged" in APP_JS
    # 多条人工标注（my_marks 列表）与逐条撤销按钮
    assert "data.my_marks" in APP_JS
    assert 'class="am-mark-del"' in APP_JS
    # 票名经 JSON.stringify 嵌 onclick 属性需 &quot; 转义（双引号会截断属性）
    assert 'deleteActionMark(${Number(data.post.id)}, ${JSON.stringify(String(m.target_name)).replace(/"/g, "&quot;")}' in APP_JS
    # 撤销按钮全撤入口（targetName=null）
    assert "deleteActionMark(${Number(data.post.id)}, null, 0)" in APP_JS
    # 生效行内「已生效」徽章
    assert 'tag-pending-badge is-approved' in APP_JS


def test_action_mark_modal_llm_action_preselect_static():
    """LLM 自动标注的操作词预选进表单：auto_tags 命中词表即预选操作并预填个股，
    我的标注（人工）优先于自动预选；命中标签高亮与预选提示样式齐备。"""
    # auto_tags 里命中操作词表的第一个标签被解析为预选操作
    assert "autoTags.find((t) => actions.includes(t))" in APP_JS
    # 人工优先：有我的标注用我的，否则落到 LLM 自动标注的操作
    assert "_actionMarkPick = myPick ? myPick.action : autoAction;" in APP_JS
    # 个股预填链：时间线预填 > 我的标注标的 > 自动标签里的股票名
    assert '(myPick ? myPick.target_name : "") || stockTags[0]' in APP_JS
    # 预选提示 + 人工改选后提示作废、自动标注区高亮跟随改选
    assert "已按自动标注预选" in APP_JS
    assert "if (hint) hint.remove();" in APP_JS
    assert '"#action-mark-mask .am-auto-tags .cat-tag"' in APP_JS
    for cls in (".am-auto-tags .cat-tag.on", ".am-auto-hint"):
        assert cls in STYLE_CSS, f"style.css 缺 {cls}"


def test_post_card_mark_entry_and_chip():
    """消息卡：授权用户出「标注」入口；生效标注以普通标签款融入标签行
    （与 LLM 标签同款、去重、不突出人工来源），未生效出「标注中」虚线角标。"""
    post_card = APP_JS[APP_JS.index("function postCard"):APP_JS.index("function mxMarkChip")]
    assert "can_mx_action_mark" in post_card
    assert "openActionMarkModal(${post.id})" in post_card
    # 入口与「查看原始消息」同款：纯链接 + 右箭头，不再是 cat 胶囊标签款
    assert '标注 ${CHEVRON_RIGHT_ICON}</a>' in post_card
    assert 'href="#" class="cat" data-post-id' not in post_card
    chip = APP_JS[APP_JS.index("function mxMarkChip"):APP_JS.index("function renderPostTagChips")]
    # 生效：与 LLM 标签同款 cat-tag（am-mark-tag 供裁决后就地重画定位），
    # 无「人工:」前缀、无实心高亮
    assert "cat-tag" in chip and "am-mark-tag" in chip
    assert "人工:" not in chip and "is-effective" not in chip
    # 去重：与消息已有标签（post.tags）及多标之间（mxMarkLabels Set 收敛）
    assert "post.tags" in chip and "mxMarkLabels(" in chip
    labels = APP_JS[APP_JS.index("function mxMarkLabels"):APP_JS.index("function mxMarkChip")]
    assert "seen" in labels and "非操作" in labels  # none 操作出「非操作」标签
    # 未生效：虚线「标注中 n/m」，生效优先展示，多生效逐条展开
    assert "is-pending" in chip and "标注中" in chip
    assert chip.index("m.effective") < chip.index("m.total")
    assert "effList" in chip


def test_me_flag_consumed_in_app():
    """/api/me 的 can_mx_action_mark 至少被 postCard 消费（state.user 挂载）。"""
    assert "state.user?.can_mx_action_mark" in APP_JS


def test_mxc_timeline_manual_badge_and_mark_entry():
    """大V持仓页时间线：manual 来源出「人工」徽章；可标注者有就地标注按钮。"""
    assert 'e.source === "manual"' in MXC_JS
    assert "mxc-src-manual" in MXC_JS
    assert "openActionMarkModal" in MXC_JS
    assert "can_mx_action_mark" in MXC_JS
    # 标注按钮带证据帖 id 与预填标的
    assert "e.evidence[0]" in MXC_JS and "JSON.stringify(String(e.target_name))" in MXC_JS


def test_mxc_pnl_acts_manual_flag():
    """盈亏行内操作徽章消费 actions[].manual 出「人工」角标。"""
    acts = MXC_JS[MXC_JS.index("function mxcPnlActs"):MXC_JS.index("  // 预估盈亏面板")]
    assert "a.manual" in acts
    assert "mxc-manual-badge" in acts


def test_admin_panel_config_and_recent_marks():
    """管理后台 kol.js：配置表单（白名单+一致人数）+ 最近标注表 + PUT 调用。"""
    assert 'id="mx-mark-users"' in ADMIN_KOL_JS
    assert 'id="mx-mark-agree-n"' in ADMIN_KOL_JS
    assert '"/api/admin/mx-action-marks/config"' in ADMIN_KOL_JS
    assert '"/api/admin/mx-action-marks?limit=50"' in ADMIN_KOL_JS
    assert "adminSaveMxMarkConfig" in ADMIN_KOL_JS
    assert "adminRefreshMxMarks" in ADMIN_KOL_JS
    # handler 从 kolView 解构（app.js 挂全局）+ 注册进 INLINE_HANDLERS
    assert "adminSaveMxMarkConfig," in APP_JS
    assert re.search(r"^\s+adminRefreshMxMarks,$", INLINE_HANDLERS, re.M)


def test_mark_styles_present():
    """CSS：卡片「标注中」虚线角标（生效标注走普通标签款无专属样式）
    + 弹窗表单 + 时间线人工徽章样式齐全。"""
    for cls in (".am-chip.is-pending", ".am-target",
                ".am-act-btn.on", ".am-mark-row", ".am-suggest",
                ".am-auto", ".am-auto-tags", ".am-mark-del", ".am-mark-row.is-effective"):
        assert cls in STYLE_CSS, f"style.css 缺 {cls}"
    assert ".am-chip.is-effective" not in STYLE_CSS  # 生效高亮款已随普通标签化移除
    for cls in (".mxc-src-manual", ".mxc-mark-btn", ".mxc-manual-badge"):
        assert cls in MXC_CSS, f"mx-kol-holdings.css 缺 {cls}"
