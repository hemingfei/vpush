"""MX 大V观点截图页：外部无头浏览器专用的静态 HTML + 时段清单。

设计边界：本系统只负责把指定交易日/时段的观点渲染成**零 JS、无登录态
（token 即凭据）**的静态 HTML 供外部系统截图；截图排程、图片生成、发布到
知识星球等平台全部由外部系统完成。对外契约：

- 整天/单时段页  GET /api/mx-shot/{token}?day=YYYY-MM-DD[&slot=HHMM][&theme=]
- 时段清单       GET /api/mx-shot/{token}/manifest?day=YYYY-MM-DD

视觉口径：与现网研判页观点流**一模一样**——行 DOM 逐字复刻
mx-views.js 的 mxvFeedItemHtml（时间/多空徽标/操作/标的/大V/摘要 六列网格，
时段两列报纸流），样式直接链接现网同源的 design-tokens/style/mx-views
三个 CSS（稳定名，内容随现网样式更新），主题走 html.theme-dark 同一机制。

时段口径与研判页流视图完全一致（mxvFeedBucketKey）：按观点发生时间向下
取整到整点/半点（00/30）分桶，缺 occurred_at 的进「—」组垫底。manifest.slots
供外部系统判断时段是否已被研判管线覆盖（存在 snapshot_at 晚于时段结束的
批次即基本齐了，再加缓冲再截图），避免截到半截内容。
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

CN_TZ = timezone(timedelta(hours=8))

_BUCKET_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2})")

# token 页参数 → 内部规范值；非法返回 None（路由层转 422）
_SLOT_RE = re.compile(r"^([01]\d|2[0-3])([0-5]\d)$")

# 现网同源样式表（稳定名）：静态挂载对无哈希路径按内容每次校验，永远与现网一致
_CSS_FILES = ("vendor/design-tokens.css", "style.css", "mx-views.css")


def normalize_slot(value: str) -> str | None:
    """slot 参数规范成 "HHMM"（时段起点，必须落在整点/半点）；空串合法（=全天）。"""
    s = str(value or "").strip().replace(":", "")
    if not s:
        return ""
    if not _SLOT_RE.fullmatch(s) or int(s[2:]) % 30 != 0:
        return None
    return s


def bucket_of(occurred_at: str) -> tuple[str, str, str]:
    """→ (key "YYYY-MM-DD HH:MM", label "HH:MM", end "HH:MM")；无时间 → ("", "—", "")。

    与前端 mxvFeedBucketKey 同口径：向下取整到 :00/:30，end = 起点+29 分钟
    （前端时段标题即「09:30~09:59」样式）。
    """
    m = _BUCKET_RE.match(str(occurred_at or ""))
    if not m:
        return ("", "—", "")
    day_s, hh, mm = m.groups()
    start = int(hh) * 60 + int(mm)
    frm = start - start % 30
    fmt = lambda mins: f"{mins // 60:02d}:{mins % 60:02d}"  # noqa: E731
    return (f"{day_s} {fmt(frm)}", fmt(frm), fmt(frm + 29))


def group_slots(opinions: list[dict]) -> list[dict]:
    """观点按时段分桶：新时段在前、批内按发生时间倒序（同前端流视图口径）。

    每组带 key/start/end/ops 与多空中性计数；缺 occurred_at 的 key="" 自然垫底。
    """
    groups: dict[str, dict] = {}
    for o in opinions:
        key, label, end = bucket_of(o.get("occurred_at") or "")
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"key": key, "start": label, "end": end, "ops": [],
                               "bull": 0, "bear": 0, "neutral": 0}
        g["ops"].append(o)
        if o.get("direction") == "bull":
            g["bull"] += 1
        elif o.get("direction") == "bear":
            g["bear"] += 1
        else:
            g["neutral"] += 1
    out = sorted(groups.values(), key=lambda g: g["key"], reverse=True)
    for g in out:
        g["ops"].sort(key=lambda o: (str(o.get("occurred_at") or ""), int(o.get("id") or 0)),
                      reverse=True)
    return out


def _esc(v) -> str:
    return html.escape(str(v if v is not None else ""), quote=True)


def _kol_short(name: str) -> str:
    # 同前端 mxvFeedItemHtml：大V名最多展示 6 字，尾字为开口括号时一并去掉再省略
    if len(name) <= 6:
        return name
    return re.sub(r"[（(【\[]$", "", name[:6]) + "…"


def _item_html(o: dict) -> str:
    # 逐字复刻 mx-views.js mxvFeedItemHtml 的行结构（fresh 入场动画除外，截图无意义）
    name = str(o.get("kol_name") or "")
    direction = str(o.get("direction") or "neutral")
    badge = "↑看多" if direction == "bull" else "↓看空" if direction == "bear" else "中性"
    action = str(o.get("action") or "")
    occurred = str(o.get("occurred_at") or "")[11:16]
    return (f'<div class="mxv-feed-item" data-mxv-hl="{_esc(o.get("target_type") or "")}:{_esc(o.get("target_name") or "")}"'
            f' data-kol-id="{_esc(o.get("kol_id") or "")}">'
            f'<span class="t" style="color:var(--mxv-accent)">{_esc(occurred)}</span>'
            f'<span class="mxv-badge {_esc(direction)}">{_esc(badge)}</span>'
            + (f'<span class="mxv-badge act" title="{_esc(action)}">{_esc(action)}</span>'
               if action else "<span></span>")
            + f'<span class="target" data-act="target" style="color:var(--mxv-text)" title="{_esc(o.get("target_name") or "")}">{_esc(o.get("target_name") or "")}</span>'
            f'<span data-act="kol" style="color:var(--mxv-muted)" title="{_esc(name)}">· {_esc(_kol_short(name))}</span>'
            f'<span class="sum" style="color:var(--mxv-faint);overflow:hidden;text-overflow:ellipsis;white-space:nowrap"'
            f' title="{_esc(o.get("summary") or "")}">{_esc(o.get("summary") or "")}</span></div>')


def _slot_html(g: dict) -> str:
    # 时段容器 id 供外部按元素截图（#slot-0930）；包一层无样式 div 不改变现网视觉
    dom_id = "slot-" + (g["key"].split(" ")[-1].replace(":", "") if g["key"] else "none")
    label = f"{g['start']}~{g['end']}" if g["end"] else g["start"]
    ops = g["ops"]
    cut = (len(ops) + 1) // 2  # 左列 = 较新一半；最早一条落在右列底部（同前端）
    cols = (f'<div class="mxv-feed-col">{"".join(_item_html(o) for o in ops[:cut])}</div>'
            f'<div class="mxv-feed-col">{"".join(_item_html(o) for o in ops[cut:])}</div>'
            if len(ops) > 1 else
            f'<div class="mxv-feed-col">{"".join(_item_html(o) for o in ops)}</div>')
    return (f'<div class="mxv-shot-slot" id="{dom_id}">'
            f'<div class="mxv-feed-sep"><span>时段 {label} · {len(ops)} 条</span></div>'
            f'<div class="mxv-feed-cols{"" if len(ops) > 1 else " single"}">{cols}</div></div>')


def _css_tags(inline: bool) -> str:
    if not inline:
        return "\n".join(f'<link rel="stylesheet" href="/{f}">' for f in _CSS_FILES)
    static = Path(__file__).parent / "static"
    return "\n".join(f"<style>{(static / f).read_text(encoding='utf-8')}</style>"
                     for f in _CSS_FILES)


def render_page(*, day: str, slot: str, theme: str, opinions: list[dict],
                inline_assets: bool = False) -> str:
    """渲染与现网观点流同构的静态 HTML。slot 为空 = 全天所有时段。

    inline_assets 供离线预览（scripts/dev_mx_shot_preview.py）把现网 CSS 内嵌；
    页面路由默认走 <link> 同源引用，样式永远与现网一致。
    """
    slots = group_slots(opinions)
    if slot:
        hhmm = f"{slot[:2]}:{slot[2:]}"
        slots = [g for g in slots if g["start"] == hhmm]
    body = ("".join(_slot_html(g) for g in slots)
            if slots else '<div class="mxv-empty">'
            + ("该时段暂无观点" if slot else "当日暂无观点") + "</div>")
    dark = theme != "light"
    title = f"大V实时观点 {day}" + (f" {slots[0]['start']}~{slots[0]['end']}" if slot and slots else "")
    html_class = ' class="theme-dark"' if dark else ""
    return f"""<!doctype html>
<html lang="zh-CN"{html_class}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{_esc(title)}</title>
{_css_tags(inline_assets)}
</head>
<body>
<div class="mxv-root">
  <div id="mxv-feed">{body}</div>
</div>
</body>
</html>"""


def build_manifest(*, day: str, opinions: list[dict], batches: list[dict],
                   days: list[dict], generated_at: str | None = None) -> dict:
    """时段清单 JSON：外部排程据此挑时段、判断研判覆盖、按 count 跳过空时段。"""
    generated_at = generated_at or datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    slots = sorted(group_slots(opinions), key=lambda g: g["key"])
    meta = sorted(batches, key=lambda b: str(b.get("snapshot_at") or ""))
    return {
        "day": day,
        "generated_at": generated_at,
        "total_opinions": len(opinions),
        "latest_snapshot_at": str(meta[-1]["snapshot_at"]) if meta else "",
        "latest_seq": int(meta[-1]["seq"] or 0) if meta else 0,
        "batches": [{"snapshot_at": str(b["snapshot_at"]), "seq": int(b["seq"] or 0),
                     "kind": b["kind"], "message_count": int(b["message_count"] or 0)}
                    for b in meta],
        "slots": [{"key": g["key"], "start": g["start"], "end": g["end"],
                   "count": len(g["ops"]), "bull": g["bull"], "bear": g["bear"],
                   "neutral": g["neutral"]} for g in slots],
        "days": [{"trading_day": str(d["trading_day"]), "snapshots": int(d["snapshots"] or 0)}
                 for d in days],
    }
