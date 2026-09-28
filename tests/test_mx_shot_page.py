"""MX 观点截图页（/api/mx-shot）：外部无头浏览器截图用，token 即凭据。

视觉契约：与现网研判页观点流一模一样（同源 CSS + 同构行 DOM），测试同时
断言关键类名/文案，防止渲染口径与 mx-views.js 漂移。
"""
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Config
from app.main import create_app

DAY = "2026-09-04"


def make_client(token="tok-shot"):
    config = Config(mx_shot_token=token)
    tmp = tempfile.mkdtemp()
    app = create_app(config=config, db_path=Path(tmp) / "shot.db")
    return TestClient(app)


def _op(kol_id, ttype="topic", name="固态电池", **kw):
    base = {
        "kol_id": kol_id, "target_type": ttype, "target_name": name,
        "direction": "bull", "action": "", "confidence": "high",
        "summary": "订单爆了", "evidence_post_ids": [11],
        "occurred_at": f"{DAY} 09:42:10",
    }
    base.update(kw)
    return base


def seed(db):
    kol = db.add_kol("mx", "李四", "room0")
    bid1 = db.upsert_mx_view_batch(DAY, "09:30", "live")
    db.replace_mx_opinions(bid1, [
        _op(kol_id=kol, occurred_at=f"{DAY} 09:42:10"),
        _op(kol_id=kol, ttype="stock", name="XX股份", action="建仓", direction="bear",
            occurred_at=f"{DAY} 10:05:00"),  # 10:00 时段
        _op(kol_id=kol, name="机器人", direction="neutral", action="观察",
            occurred_at=""),  # 缺时间 →「—」组
    ])
    db.upsert_mx_view_snapshot(DAY, "09:30", 1, "live",
                               {"seq": 1, "snapshot_at": "09:30", "message_count": 3}, bid1)
    return kol


def test_shot_page_disabled_without_token():
    client = make_client(token="")
    seed(client.app.state.db)
    r = client.get("/api/mx-shot/whatever")
    assert r.status_code == 404
    r = client.get("/api/mx-shot/whatever/manifest")
    assert r.status_code == 404


def test_shot_page_wrong_token_404():
    client = make_client()
    seed(client.app.state.db)
    assert client.get("/api/mx-shot/bad").status_code == 404
    assert client.get("/api/mx-shot/bad/manifest").status_code == 404


def test_shot_page_renders_live_feed_markup():
    """视觉契约：行 DOM 与现网 mxvFeedItemHtml 同构，样式链接现网同源 CSS。"""
    client = make_client()
    seed(client.app.state.db)
    r = client.get(f"/api/mx-shot/tok-shot?day={DAY}")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    body = r.text
    # 暗色主题默认（与现网研判页截图一致）+ 现网同源样式表
    assert '<html lang="zh-CN" class="theme-dark">' in body
    assert '<link rel="stylesheet" href="/vendor/design-tokens.css">' in body
    assert '<link rel="stylesheet" href="/style.css">' in body
    assert '<link rel="stylesheet" href="/mx-views.css">' in body
    assert "noindex" in body
    # 时段分桶口径（09:42 → 09:30~09:59；10:05 → 10:00~10:29；缺时间 →「—」）
    assert 'id="slot-0930"' in body and 'id="slot-1000"' in body and 'id="slot-none"' in body
    assert "时段 09:30~09:59 · 1 条" in body and "时段 10:00~10:29 · 1 条" in body
    assert "时段 — · 1 条" in body
    # 行结构：六列网格（时间/多空徽标/操作/标的/大V/摘要），方向配色与现网同源
    assert 'class="mxv-feed-item"' in body
    assert '<span class="mxv-badge bull">↑看多</span>' in body
    assert '<span class="mxv-badge bear">↓看空</span>' in body
    assert '<span class="mxv-badge neutral">中性</span>' in body
    assert '<span class="mxv-badge act" title="建仓">建仓</span>' in body
    assert "· 李四" in body
    assert "固态电池" in body and "XX股份" in body


def test_shot_page_slot_filter():
    client = make_client()
    seed(client.app.state.db)
    r = client.get("/api/mx-shot/tok-shot?day=2026-09-04&slot=0930")
    assert r.status_code == 200
    body = r.text
    assert 'id="slot-0930"' in body
    assert "XX股份" not in body  # 10:00 时段不出现
    assert "固态电池" in body


def test_shot_page_param_validation():
    client = make_client()
    seed(client.app.state.db)
    assert client.get("/api/mx-shot/tok-shot?slot=0913").status_code == 422  # 非整点/半点
    assert client.get("/api/mx-shot/tok-shot?slot=abc").status_code == 422
    assert client.get("/api/mx-shot/tok-shot?day=2026-9-4").status_code == 422
    assert client.get("/api/mx-shot/tok-shot?day=2026-09-04").status_code == 200


def test_shot_page_empty_day_defaults_to_latest():
    client = make_client()
    r = client.get("/api/mx-shot/tok-shot")  # 无任何数据：day 缺省 → 空态页而非 404
    assert r.status_code == 200
    assert "当日暂无观点" in r.text and "mxv-empty" in r.text


def test_shot_manifest():
    client = make_client()
    seed(client.app.state.db)
    r = client.get(f"/api/mx-shot/tok-shot/manifest?day={DAY}")
    assert r.status_code == 200
    m = r.json()
    assert m["day"] == DAY
    assert m["latest_snapshot_at"] == "09:30" and m["latest_seq"] == 1
    assert m["total_opinions"] == 3
    assert m["batches"] == [{"snapshot_at": "09:30", "seq": 1, "kind": "live",
                             "message_count": 3}]
    slots = {s["start"]: s for s in m["slots"]}
    assert slots["09:30"]["count"] == 1 and slots["09:30"]["bull"] == 1
    assert slots["10:00"]["count"] == 1 and slots["10:00"]["bear"] == 1
    assert slots["—"]["count"] == 1
    assert m["days"] == [{"trading_day": DAY, "snapshots": 1}]


def test_shot_manifest_day_defaults_to_latest():
    client = make_client()
    seed(client.app.state.db)
    m = client.get("/api/mx-shot/tok-shot/manifest").json()
    assert m["day"] == DAY  # 缺省 = 最近有快照的交易日


def test_shot_page_theme_param():
    client = make_client()
    seed(client.app.state.db)
    dark = client.get("/api/mx-shot/tok-shot")
    assert 'class="theme-dark"' in dark.text  # 默认暗色（现网研判页同款）
    light = client.get("/api/mx-shot/tok-shot?theme=light")
    assert "theme-dark" not in light.text
