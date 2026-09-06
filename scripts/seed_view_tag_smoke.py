"""UI 冒烟种子：临时库里造一条带观点回流标签的 MX 帖 + 一条待审标签。"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import DB
from app import mx_view_tagging

db_path = Path(tempfile.gettempdir()) / "vpush-smoke" / "smoke.db"
db_path.parent.mkdir(exist_ok=True)
if db_path.exists():
    db_path.unlink()
db = DB(str(db_path))

kol = db.add_kol("mx", "李四", "room0")
pid = db.insert_post(
    platform="mx", kol_id=kol, external_id="m1", title="", url="",
    content="宁德时代订单爆了，先建仓。固态电池这条线今天也很强势，赛博努巴有人说要翻倍。",
    published_at="2026-09-06 09:38:00",
)
db.set_stock_names(["宁德时代"])
mx_view_tagging.set_view_tagging_enabled(db, True)
mx_view_tagging.apply_view_tags(db, [
    {"kol_id": kol, "target_type": "stock", "target_name": "宁德时代", "direction": "bull",
     "action": "建仓", "confidence": "high", "summary": "s", "evidence_post_ids": [pid],
     "occurred_at": "2026-09-06 09:38:00"},
    {"kol_id": kol, "target_type": "topic", "target_name": "固态电池", "direction": "bull",
     "action": "", "confidence": "high", "summary": "s", "evidence_post_ids": [pid],
     "occurred_at": "2026-09-06 09:38:00"},
    {"kol_id": kol, "target_type": "stock", "target_name": "赛博努巴", "direction": "bear",
     "action": "", "confidence": "high", "summary": "s", "evidence_post_ids": [pid],
     "occurred_at": "2026-09-06 09:38:00"},
], topic_hints=["固态电池"])
print(f"db={db_path} post={pid} kol={kol}")
