"""MX 平台接入：消息解析兜底、房间同步、广场显隐、配置热加载。"""
import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace

from app.config import MxConfig
from app.db import DB
from app.fetchers.base import Post
from app.fetchers.mx.fetcher import MxFetcher, normalize_mx_text
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


def test_file_message_with_image_url_treated_as_pic():
    """file 消息 URL 是图片格式（png/jpg 等）时按图片处理，不能整条丢掉。"""
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    raw = {
        "id": 11,
        "rid": 101,
        "msg": '[{"type": "text", "msg": ""}, {"type": "file", "url": "https://img.test/a.png?bizType=im", "name": "清北"}]',
        "createtime": 1700000000000,
    }
    post = fetcher._parse_message_to_post(raw, kol)
    assert post is not None
    assert post.images and ".png" in post.images[0]


def test_file_message_image_detected_by_name_extension():
    """URL 没有扩展名但文件名带图片扩展名时同样按图片处理。"""
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    raw = {
        "id": 12,
        "rid": 101,
        "msg": '[{"type": "file", "url": "https://img.test/download?id=1", "name": "清北.JPG"}]',
        "createtime": 1700000000000,
    }
    post = fetcher._parse_message_to_post(raw, kol)
    assert post is not None
    assert len(post.images) == 1


def test_file_message_without_extension_treated_as_pic():
    """URL 没有任何扩展名时也按图片处理（平台转存图常不带格式后缀）。"""
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    raw = {
        "id": 14,
        "rid": 101,
        "msg": '[{"type": "file", "url": "https://static.dingtalk.com/media/lALPM25nMDmpznskzQED_0A0A0A", "name": "清北"}]',
        "createtime": 1700000000000,
    }
    post = fetcher._parse_message_to_post(raw, kol)
    assert post is not None
    assert len(post.images) == 1


def test_file_message_no_url_ext_file_name_ext_respected():
    """URL 无后缀但文件名带非图片扩展名（如 .pdf）时仍是文件，不按图片处理。"""
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    raw = {
        "id": 15,
        "rid": 101,
        "msg": '[{"type": "file", "url": "https://img.test/download?id=1", "name": "报告.pdf"}]',
        "createtime": 1700000000000,
    }
    post = fetcher._parse_message_to_post(raw, kol)
    assert post is None


def test_file_message_non_image_still_dropped():
    """file 消息不是图片格式（如 pdf）时维持原行为：解析不出内容则丢弃。"""
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    raw = {
        "id": 13,
        "rid": 101,
        "msg": '[{"type": "file", "url": "https://img.test/doc.pdf", "name": "文档"}]',
        "createtime": 1700000000000,
    }
    post = fetcher._parse_message_to_post(raw, kol)
    assert post is None


def test_json_encoded_plain_string_msg():
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    raw = {"id": 10, "rid": 101, "msg": '"纯文本"', "createtime": 1700000000000}
    post = fetcher._parse_message_to_post(raw, kol)
    assert post is not None and post.content == "纯文本"


# ---- 正文换行归一化 ----

def test_normalize_mx_text_unescapes_and_collapses():
    """字面量「反斜杠+n/r」与真实 CR/CRLF 统一还原成单个换行；连续换行压成一个。"""
    assert normalize_mx_text("第一段\\n\\n第二段") == "第一段\n第二段"
    assert normalize_mx_text("第一段\\r\\n第二段") == "第一段\n第二段"
    assert normalize_mx_text("A\r\n\r\nB\r\nC") == "A\nB\nC"
    assert normalize_mx_text("A\rB") == "A\nB"
    # 真实 CR 后跟字面量 \n（编辑前缀场景）→ 归并成一个换行
    assert normalize_mx_text("前缀\r\\n正文") == "前缀\n正文"
    # 只有空白字符（含全角空格）的行按空行处理
    u3000 = "\u3000"
    assert normalize_mx_text(f"A{u3000}\n{u3000}\nB") == f"A{u3000}\nB"
    assert normalize_mx_text("A\n   \nB") == "A\nB"
    # 无换行内容原样保留，结果幂等
    assert normalize_mx_text("普通文本") == "普通文本"
    once = normalize_mx_text("A\n\n\\nB")
    assert normalize_mx_text(once) == once


def test_message_newlines_normalized_in_post():
    """入库正文：服务端双重转义的字面量换行还原，跨 text 片段的连续换行也折叠。"""
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    raw = {
        "id": 21,
        "rid": 101,
        "msg": '[{"type": "text", "msg": "第一段\\\\n\\\\n第二段"}, {"type": "text", "msg": "\\\\n\\\\n第三段"}]',
        "createtime": 1700000000000,
    }
    post = fetcher._parse_message_to_post(raw, kol)
    assert post.content == "第一段\n第二段\n第三段"


def test_real_crlf_message_normalized():
    """服务端正常转义（单层 \r\n）的消息解码后是真实 CRLF，同样折叠为单个换行。"""
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    raw = {
        "id": 23,
        "rid": 101,
        "msg": '[{"type": "text", "msg": "A\\r\\n\\r\\nB"}]',
        "createtime": 1700000000000,
    }
    post = fetcher._parse_message_to_post(raw, kol)
    assert post.content == "A\nB"


def test_blank_only_message_dropped():
    """整条消息只剩换行时归一化为空正文 → 无内容无图直接丢弃，不推空帖。"""
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    raw = {
        "id": 22,
        "rid": 101,
        "msg": '[{"type": "text", "msg": "\\\\n\\\\n"}]',
        "createtime": 1700000000000,
    }
    assert fetcher._parse_message_to_post(raw, kol) is None


def test_mx_content_newline_backfill_migration():
    """历史 MX 帖的脏换行在启动迁移时修复；其他平台正文不受影响。"""
    tmp = tempfile.mkdtemp()
    path = Path(tmp) / "mx.db"
    db = DB(path)
    kid = db.add_kol("mx", "房间A", "101")
    dirty_id = db.insert_post(
        platform="mx",
        kol_id=kid,
        external_id="m1",
        title="",
        content="第一行\r\n第二行\\n\\n第三行",
        url="",
        published_at="2026-08-28 10:00:00",
    )
    sys_id = db.insert_post(
        platform="system",
        kol_id=kid,
        external_id="s1",
        title="",
        content="A\n\nB",
        url="",
        published_at="2026-08-28 10:00:00",
    )
    db.close()

    db = DB(path)  # 重新打开触发 _migrate
    assert db.get_post(dirty_id)["content"] == "第一行\n第二行\n第三行"
    assert db.get_post(sys_id)["content"] == "A\n\nB"
    db.close()


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


# ---- 加密：UTF-16 码元视角（消息含 emoji 时解密失败的历史 bug） ----

def _merge_pairs_like_transport(s: str) -> str:
    """模拟 JSON/HTTP 传输对服务端字符串的影响：相邻合法代理对合并为单个
    增补平面字符（Node 把合法代理对按标准 UTF-8 4 字节发出）。"""
    out = []
    i = 0
    while i < len(s):
        o = ord(s[i])
        if 0xD800 <= o <= 0xDBFF and i + 1 < len(s) and 0xDC00 <= ord(s[i + 1]) <= 0xDFFF:
            out.append(chr(0x10000 + ((o - 0xD800) << 10) + (ord(s[i + 1]) - 0xDC00)))
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def test_crypto_surrogate_pair_expand_combine_roundtrip():
    from app.fetchers.mx import crypto

    text = "a\U0001F600b中文🎉"
    units = crypto._to_utf16_units(text)
    # 增补平面字符被拆成一对码元
    assert len(units) == len(text) + 2
    assert crypto.combine_surrogate_pairs(units) == text
    # 无增补平面字符的文本必须原样通过
    assert crypto._to_utf16_units("abc中文") == "abc中文"


def test_decrypt_api_data_with_emoji_content():
    """端到端：服务端按 JS 码元压缩 + 明文含 emoji，解密必须还原原始数据。

    历史 bug：密文经传输后代理对合并成增补平面字符，Python 的解压视角与
    JS charCodeAt 错位，decrypt_api_data 返回 None，消息列表拿到空数组。
    """
    import base64
    import json as jsonlib

    import lzstring
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    from app.fetchers.mx import crypto

    payload = {
        "code": 200,
        "list": [{"id": 1, "msg": '[{"type":"text","msg":"👍开盘🎉拉升"}]'}],
    }
    date_str = crypto.get_beijing_date(0).strftime("%Y-%m-%d")
    key, iv = crypto.generate_key(date_str)
    plaintext = jsonlib.dumps(payload, ensure_ascii=False).encode("utf-8")
    # 复刻服务端加密管线：AES-CBC 加密 → base64 → 按 JS UTF-16 码元 LZ-String 压缩
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    b64 = base64.b64encode(ciphertext).decode("ascii")
    compressed = lzstring.LZString.compress(crypto._to_utf16_units(b64))
    # 传输层合并代理对后的密文（真实客户端收到的形态）
    transported = _merge_pairs_like_transport(compressed)
    assert crypto.decrypt_api_data(transported) == payload
