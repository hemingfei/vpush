# -*- coding: utf-8 -*-
"""开发冒烟：用真实 dev 库渲染截图页 HTML 到临时目录（只读查询，不写库）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import DB
from app import mx_shot_page

db = DB("data/dav.db")
day = db.mx_view_days()[0]["trading_day"]
out = Path(sys.argv[1] if len(sys.argv) > 1 else "mx_shot_preview.html")
html_text = mx_shot_page.render_page(
    day=day, slot="", theme="dark",
    opinions=db.list_mx_opinions(day),
    inline_assets=True,  # 离线预览：内嵌现网 CSS，不依赖站点
)
out.write_text(html_text, encoding="utf-8")
print(f"rendered {day} -> {out} ({len(html_text)} chars)")
