"""MX 平台接入：消息解析兜底、房间同步、广场显隐、配置热加载。"""
import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace

from app.config import MxConfig
from app.db import DB
from app.fetchers.base import Post
from app.fetchers.mx.fetcher import MxFetcher
from app.fetchers.mx.ws import MxWsClient
from app.plaza import filter_plaza_kol_rows, kol_plaza_hidden
from app.services.mx_sync import MXRoomSyncService


def make_db() -> DB:
    tmp = tempfile.mkdtemp()
    return DB(Path(tmp) / "test.db")


def make_fetcher(db, page_size=50):
    config = SimpleNamespace(
        api_base="https://mx.test/business-api/5",
        token="t",
        page_size=page_size,
        max_history_pages=5,
        ws_enabled=False,
    )
    return MxFetcher(config, db)


def make_kol(db):
    kid = db.add_kol("mx", "房间A", "101")
    return db.get_kol(kid)


def msg(mid, text, rid=101, createtime=1700000000000):
    return {"id": mid, "rid": rid, "msg": text, "createtime": createtime}


# ---- 消息解析兜底 ----

def test_missing_id_gets_deterministic_external_id():
    """缺 id 的消息必须生成确定性 external_id，否则全部撞 '' 唯一键被静默吞掉。"""
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    raw = {"rid": 101, "msg": "无id消息", "createtime": 1700000000000}

    post1 = fetcher._parse_message_to_post(dict(raw), kol)
    post2 = fetcher._parse_message_to_post(dict(raw), kol)
    assert post1.external_id != ""
    assert post1.external_id == post2.external_id  # 同一消息两次到达 → 同一键 → 去重有效


def test_missing_id_different_content_different_key():
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    p1 = fetcher._parse_message_to_post({"rid": 101, "msg": "aaa", "createtime": 1}, kol)
    p2 = fetcher._parse_message_to_post({"rid": 101, "msg": "bbb", "createtime": 1}, kol)
    assert p1.external_id != p2.external_id


def test_unparsable_message_dropped_not_json_dumped():
    """解析不出文本/图片的消息直接丢弃，不能把整包 JSON 当正文推送。"""
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    raw = {"rid": 101, "msg": '{"type": "unknown", "payload": {"x": 1}}', "createtime": 1}
    post = fetcher._parse_message_to_post(raw, kol)
    assert post is None


def test_pic_message_keeps_images_and_text():
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    raw = {
        "id": 9,
        "rid": 101,
        "msg": '[{"type": "text", "msg": "看图"}, {"type": "pic", "url": "https://img.test/a.jpg"}]',
        "createtime": 1700000000000,
    }
    post = fetcher._parse_message_to_post(raw, kol)
    assert post.content == "看图"
    assert post.external_id == "9"


def test_json_encoded_plain_string_msg():
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    raw = {"id": 10, "rid": 101, "msg": '"纯文本"', "createtime": 1700000000000}
    post = fetcher._parse_message_to_post(raw, kol)
    assert post is not None and post.content == "纯文本"


# ---- WS 消息解析回退 ----

def test_ws_plain_long_content_keeps_original_fields(monkeypatch):
    """dict 消息带明文长 content 且解密失败时，必须保留原始字段（rid 不能被埋进 raw）。"""
    import app.fetchers.mx.ws as mx_ws

    monkeypatch.setattr(mx_ws, "decrypt_ws_data", lambda s: None)
    client = mx_ws.MxWsClient(SimpleNamespace(), lambda m: None)
    parsed = client._parse_message({"rid": "5", "content": "x" * 80, "id": 3})
    assert parsed["rid"] == "5" and parsed["id"] == 3


def test_ws_plain_long_data_keeps_original_fields(monkeypatch):
    import app.fetchers.mx.ws as mx_ws

    monkeypatch.setattr(mx_ws, "decrypt_ws_data", lambda s: None)
    client = mx_ws.MxWsClient(SimpleNamespace(), lambda m: None)
    parsed = client._parse_message({"rid": "6", "data": "y" * 80})
    assert parsed["rid"] == "6"


def test_ws_list_payload_distributes_each_item(monkeypatch):
    """事件一次送达一批消息（list）时逐条分发，且每条带 _receivedAt。"""
    calls = []
    client = MxWsClient(SimpleNamespace(), calls.append)
    client._parse_message = lambda data: [{"rid": "5", "id": 1}, {"rid": "5", "id": 2}]
    asyncio.run(client._handle_message({"anything": 1}))
    assert [m["id"] for m in calls] == [1, 2]
    assert all("_receivedAt" in m for m in calls)


def test_ws_short_plain_content_keeps_fields(monkeypatch):
    """短明文 content（不进解密分支）直接原样透传。"""
    client = MxWsClient(SimpleNamespace(), lambda m: None)
    parsed = client._parse_message({"rid": "7", "content": "hi", "id": 4})
    assert parsed["rid"] == "7" and parsed["id"] == 4


# ---- 房间同步 ----

def test_sync_room_creates_kol_with_fallback_name_and_intro():
    """title 为空串时用默认名；introduce 存进 extra_data。"""
    db = make_db()
    service = MXRoomSyncService(MxConfig(token="t"), db)
    service._sync_room({"id": 88, "title": "", "introduce": "介绍文本"})

    kol = db.get_kol_by_external("mx", "88")
    assert kol is not None
    assert kol["name"] == "MX Room 88"
    import json

    extra = json.loads(kol["extra_data"])
    assert extra["introduce"] == "介绍文本"
    assert extra["show_in_plaza"] is True


def test_sync_preserves_user_toggled_show_in_plaza():
    """管理员关掉房间广场显示后，再次同步不得重置为 True。"""
    import json

    db = make_db()
    kid = db.add_kol("mx", "房间B", "99")
    extra = json.loads(db.get_kol(kid)["extra_data"] or "{}")
    extra["show_in_plaza"] = False
    db.update_kol(kid, extra_data=json.dumps(extra, ensure_ascii=False))

    service = MXRoomSyncService(MxConfig(token="t"), db)
    service._sync_room({"id": 99, "title": "房间B新名"})

    kol = db.get_kol(kid)
    assert kol["name"] == "房间B新名"
    assert json.loads(kol["extra_data"])["show_in_plaza"] is False


def test_sync_rooms_blocking_closes_client(monkeypatch):
    db = make_db()
    service = MXRoomSyncService(MxConfig(token="t"), db)

    closed = []
    from app.fetchers.mx.client import MXClient

    monkeypatch.setattr(
        MXClient, "get_rooms", lambda self: [_ for _ in ()] or [{"id": 1, "title": "r"}]
    )
    monkeypatch.setattr(MXClient, "close", lambda self: closed.append(True))
    service._sync_rooms_blocking()
    assert closed == [True]
    assert db.get_kol_by_external("mx", "1") is not None


# ---- 广场显隐 ----

def test_mx_room_show_in_plaza_filters_catalog_rows():
    import json

    db = make_db()
    hidden_id = db.add_kol("mx", "隐藏房", "201")
    shown_id = db.add_kol("mx", "显示房", "202")
    other_id = db.add_kol("xueqiu", "雪球V", "203")

    extra = json.loads(db.get_kol(hidden_id)["extra_data"] or "{}")
    extra["show_in_plaza"] = False
    db.update_kol(hidden_id, extra_data=json.dumps(extra, ensure_ascii=False))

    rows = db.list_kols()
    assert kol_plaza_hidden(db, db.get_kol(hidden_id)) is True
    assert kol_plaza_hidden(db, db.get_kol(shown_id)) is False
    assert kol_plaza_hidden(db, db.get_kol(other_id)) is False

    filtered = filter_plaza_kol_rows(db, rows)
    ids = {r["id"] for r in filtered}
    assert hidden_id not in ids
    assert shown_id in ids and other_id in ids


# ---- 追平翻页 ----

class FakeMxClient:
    def __init__(self, pages):
        self.pages = pages

    def get_room_history(self, room_id, msg_id=0, limit=50):
        return self.pages.get(msg_id, [])


def test_fetch_backfills_until_known_post():
    """首页尾部出现未入库新帖时，用游标继续翻页直到撞见已入库旧帖。"""
    db = make_db()
    kol = make_kol(db)
    fetcher = make_fetcher(db, page_size=3)
    fetcher.mx_client = FakeMxClient(
        {
            0: [msg(7, "m7"), msg(6, "m6"), msg(5, "m5")],
            5: [msg(4, "m4")],  # 撞见已入库旧帖 → 停
        }
    )
    db.insert_post("mx", kol["id"], "4", "", "m4", "", "2026-01-01")

    posts = fetcher.fetch(kol)
    assert {p.external_id for p in posts} == {"7", "6", "5", "4"}


def test_fetch_no_backfill_when_tail_known():
    db = make_db()
    kol = make_kol(db)
    fetcher = make_fetcher(db, page_size=3)

    class Closed:
        def __init__(self):
            self.calls = 0

        def get_room_history(self, room_id, msg_id=0, limit=50):
            self.calls += 1
            return [msg(7, "m7"), msg(6, "m6"), msg(5, "m5")]

    fake = Closed()
    fetcher.mx_client = fake
    db.insert_post("mx", kol["id"], "5", "", "m5", "", "2026-01-01")

    posts = fetcher.fetch(kol)
    assert {p.external_id for p in posts} == {"7", "6", "5"}
    assert fake.calls == 1  # 尾帖已入库，零额外请求


def test_fetch_no_backfill_when_page_not_full():
    db = make_db()
    kol = make_kol(db)
    fetcher = make_fetcher(db, page_size=50)
    fetcher.mx_client = FakeMxClient({0: [msg(2, "m2"), msg(1, "m1")]})
    posts = fetcher.fetch(kol)
    assert {p.external_id for p in posts} == {"2", "1"}


def test_backfill_stops_when_cursor_stalls():
    """游标不前移时必须终止，避免死循环。"""
    db = make_db()
    kol = make_kol(db)
    fetcher = make_fetcher(db, page_size=2)
    calls = []

    class Stalled:
        def get_room_history(self, room_id, msg_id=0, limit=50):
            calls.append(msg_id)
            if msg_id == 0:
                return [msg(5, "m5"), msg(4, "m4")]
            return [msg(4, "m4")]  # 游标 4 → 仍返回 4，不前移

    fetcher.mx_client = Stalled()
    posts = fetcher.fetch(kol)
    assert len(calls) <= 3  # 首页 + 一次追平即停
    assert {p.external_id for p in posts} == {"5", "4"}


# ---- 配置热加载 ----

def _make_scheduler(db):
    from app.scheduler import Scheduler

    return Scheduler(
        db,
        fetchers={},
        notifiers=[],
        polling_config=SimpleNamespace(
            interval_seconds=180,
            priority_interval_seconds=60,
            notify_on_start=False,
        ),
        notifiers_config=None,
        mx_config=MxConfig(enabled=False),
    )


def test_apply_mx_config_enables_and_disables_at_runtime():
    """保存配置后无需重启：启用即注入 mx 抓取器，禁用即移除并停任务。"""
    db = make_db()
    scheduler = _make_scheduler(db)

    asyncio.run(scheduler.apply_mx_config(MxConfig(enabled=True, token="", ws_enabled=False)))
    assert "mx" in scheduler.fetchers
    assert scheduler._mx_sync_service is not None

    asyncio.run(scheduler.apply_mx_config(MxConfig(enabled=False, token="", ws_enabled=False)))
    assert "mx" not in scheduler.fetchers
    assert scheduler._mx_sync_service is None
    scheduler.stop()


def test_apply_mx_config_rebuilds_fetcher_with_new_config():
    db = make_db()
    scheduler = _make_scheduler(db)

    asyncio.run(
        scheduler.apply_mx_config(
            MxConfig(enabled=True, token="t1", page_size=30, ws_enabled=False)
        )
    )
    old = scheduler.fetchers["mx"]
    assert old.page_size == 30

    asyncio.run(
        scheduler.apply_mx_config(
            MxConfig(enabled=True, token="t2", page_size=60, ws_enabled=False)
        )
    )
    new = scheduler.fetchers["mx"]
    assert new is not old and new.page_size == 60
    scheduler.stop()


def test_update_mx_config_endpoint_hot_applies(monkeypatch):
    """PUT /admin/sources/mx 保存后必须热应用到调度器（历史 bug：需重启才生效）。"""
    import os

    import yaml
    from fastapi.testclient import TestClient

    import app.scheduler as sched_mod
    from app.config import Config
    from app.main import create_app

    tmp = tempfile.mkdtemp()
    config_path = Path(tmp) / "config.yaml"
    monkeypatch.setenv("CONFIG_PATH", str(config_path))

    calls = []
    orig_apply = sched_mod.Scheduler.apply_mx_config

    async def spy(self, mx_config):
        calls.append((self, mx_config))
        await orig_apply(self, mx_config)

    monkeypatch.setattr(sched_mod.Scheduler, "apply_mx_config", spy)
    # 测试不需要真的启动周期同步循环（避免 TestClient 循环关闭时任务悬挂告警）
    monkeypatch.setattr(
        "app.services.mx_sync.MXRoomSyncService.start_periodic_sync",
        lambda self: _noop_coroutine(),
    )

    app = create_app(config=Config(), db_path=Path(tmp) / "t.db")
    client = TestClient(app)

    code = "TESTMX01"
    client.app.state.db.add_register_code(code)
    data = client.post(
        "/api/auth/register",
        json={"username": "mxadmin", "password": "secret123", "code": code},
    ).json()
    client.app.state.db.update_user(data["user"]["id"], is_admin=True)
    headers = {"Authorization": f"Bearer {data['token']}"}

    payload = {
        "enabled": True,
        "token": "tok",
        "page_size": 33,
        "ws_enabled": False,
    }
    resp = client.put("/api/admin/sources/mx", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text

    # 配置落盘
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["sources"]["mx"]["enabled"] is True
    assert saved["sources"]["mx"]["page_size"] == 33

    # 热应用被调用，抓取器按新配置注入
    assert len(calls) == 1
    sched, applied = calls[0]
    assert applied.enabled is True and applied.page_size == 33
    assert "mx" in sched.fetchers and sched.fetchers["mx"].page_size == 33

    # 禁用后热应用移除抓取器
    resp = client.put(
        "/api/admin/sources/mx",
        json={"enabled": False, "token": "tok"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert len(calls) == 2
    assert "mx" not in sched.fetchers


async def _noop_coroutine():
    return None


# ---- WS 状态 ----

def test_ws_status_reflects_client():
    from app import scheduler as sched_mod

    db = make_db()
    fetcher = make_fetcher(db)
    fetcher.ws_client = SimpleNamespace(connected=True, last_message_at=None)
    assert fetcher.get_ws_status()["connected"] is True

    # 模块级 _mx_fetcher 必须被赋值后 get_mx_ws_status 才有数据（历史 bug：永远 False）
    sched_mod._mx_fetcher = fetcher
    try:
        assert sched_mod.get_mx_ws_status()["connected"] is True
    finally:
        sched_mod._mx_fetcher = None
    assert sched_mod.get_mx_ws_status()["connected"] is False


# ---- Post 兼容导入（保证 backfill 相关基础可用） ----

def test_post_roundtrip_for_backfill_keys():
    db = make_db()
    kid = db.add_kol("mx", "房间C", "300")
    db.insert_post("mx", kid, "5", "", "c", "", "2026-01-01")
    assert db.existing_post_keys([("mx", "5")]) == {("mx", "5")}
    assert db.existing_post_keys([("mx", "6")]) == set()


def test_batch_insert_mixed_new_and_existing():
    db = make_db()
    kid = db.add_kol("mx", "房间D", "400")
    p1 = Post(platform="mx", kol_id=kid, kol_name="房间D", external_id="1",
              title="", content="a", url="", published_at="2026-01-01")
    db.insert_posts_batch([p1])
    p1_dup = Post(platform="mx", kol_id=kid, kol_name="房间D", external_id="1",
                  title="", content="a", url="", published_at="2026-01-01")
    p2 = Post(platform="mx", kol_id=kid, kol_name="房间D", external_id="2",
              title="", content="b", url="", published_at="2026-01-01")
    ids = db.insert_posts_batch([p1_dup, p2])
    assert ids == [None, ids[1]]
    assert ids[1] is not None
