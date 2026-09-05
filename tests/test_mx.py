"""MX 平台接入：消息解析兜底、房间同步、广场显隐、配置热加载。"""
import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace

from app.config import MxConfig
from app.db import DB
from app.fetchers.base import Post
from app.fetchers.mx.fetcher import MxFetcher, looks_like_image_url, normalize_mx_text
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
    """解析不出文本/图片/文件的消息直接丢弃，不能把整包 JSON 当正文推送。"""
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
    assert post is not None
    assert post.content == "[文件]"
    assert not post.images


def test_file_message_non_image_kept_as_attachment():
    """file 消息不是图片格式（如 pdf）时保留消息并合成 [文件] 占位正文，不再整条丢弃。"""
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
    assert post is not None
    assert post.content == "[文件]"


def test_looks_like_image_url_page_hosts():
    """公众号文章/短链等纯网页宿主永不按图片处理，即使 URL 不带扩展名。"""
    assert not looks_like_image_url("https://mp.weixin.qq.com/s/EJT-9GxmmA6JrqrmXOwsZA")
    assert not looks_like_image_url("http://t.cn/AXpqDJRA")
    assert not looks_like_image_url("https://url.cn/abcd12")
    # 无后缀的真实图床 URL 仍按图片（平台转存图场景）
    assert looks_like_image_url("https://wework.qpic.cn/wwpic3az/488494_RitDJ_taTXiJBqT_")
    assert looks_like_image_url("https://img.test/a.png")


def test_page_link_file_message_kept_as_attachment():
    """微信文章链接卡片（file 项、URL 与名称都无扩展名）按附件保留，不进 images。"""
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    raw = {
        "id": 16,
        "rid": 101,
        "msg": '[{"type": "text", "msg": "转一篇"}, '
               '{"type": "file", "url": "https://mp.weixin.qq.com/s/EJT-9GxmmA6JrqrmXOwsZA", "name": "洪灝：美联储豪赌日元汇率"}]',
        "createtime": 1700000000000,
    }
    post = fetcher._parse_message_to_post(raw, kol)
    assert post is not None
    assert post.images == []
    assert post.content == "转一篇"


def test_page_link_card_without_text_gets_placeholder():
    """纯链接卡片消息（无正文）：合成 [文件] 占位，不整条丢弃也不渲染死图。"""
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    raw = {
        "id": 17,
        "rid": 101,
        "msg": '[{"type": "file", "url": "http://t.cn/AXpqDJRA", "name": "视频号"}]',
        "createtime": 1700000000000,
    }
    post = fetcher._parse_message_to_post(raw, kol)
    assert post is not None
    assert post.images == []
    assert post.content == "[文件]"


def test_file_message_confirmed_non_image_downgrades_to_attachment(monkeypatch):
    """「疑似图片」的 file 消息实测返回非图片内容（cache 返回 None）时降级为附件。"""
    import app.fetchers.mx.fetcher as mx_fetcher_module

    monkeypatch.setattr(mx_fetcher_module, "cache_image_file", lambda *args, **kwargs: None)
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    raw = {
        "id": 18,
        "rid": 101,
        "msg": '[{"type": "file", "url": "https://unknown-host.test/media/lALP123", "name": "清北"}]',
        "createtime": 1700000000000,
    }
    post = fetcher._parse_message_to_post(raw, kol)
    assert post is not None
    assert post.images == []
    assert post.content == "[文件]"


def test_pure_voice_message_kept_with_placeholder():
    """纯语音消息（只有 file 无文字）不能整条丢弃：合成 [语音] 占位正文。"""
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    raw = {
        "id": 16,
        "rid": 101,
        "msg": '[{"type": "file", "url": "https://cdn.test/a.mp3", "name": "点击播放"}]',
        "createtime": 1700000000000,
    }
    post = fetcher._parse_message_to_post(raw, kol)
    assert post is not None
    assert post.content == "[语音]"


def test_text_with_pdf_file_keeps_text():
    """文字 + PDF 附件的消息：正文保留文字，消息不丢。"""
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    raw = {
        "id": 17,
        "rid": 101,
        "msg": '[{"type": "text", "msg": "看报告"}, {"type": "file", "url": "https://img.test/doc.pdf", "name": "文档"}]',
        "createtime": 1700000000000,
    }
    post = fetcher._parse_message_to_post(raw, kol)
    assert post is not None
    assert post.content == "看报告"


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


# ---- WS 重连策略：12 秒后仅重连一次，失败永久放弃 ----

def test_ws_gives_up_after_one_failed_reconnect(monkeypatch):
    """断线后只重连一次：重连再失败即置 gave_up 并触发回调，不再无限重试。"""
    import app.fetchers.mx.ws as mx_ws

    monkeypatch.setattr(mx_ws, "_reconnect_delay", lambda: 0.01)
    give_ups = []
    client = MxWsClient(
        SimpleNamespace(), lambda m: None,
        on_give_up=lambda r, t: give_ups.append((r, t)),
    )
    attempts = {"n": 0}

    async def failing_connect():
        attempts["n"] += 1
        raise RuntimeError("connect refused")

    client.connect = failing_connect
    asyncio.run(asyncio.wait_for(client.run_forever(), timeout=5))

    assert attempts["n"] == 2  # 首连 + 唯一一次重连，绝没有第三次
    assert client.gave_up is True
    assert client.running is False
    assert give_ups == [("connect refused", False)]


def test_ws_give_up_supports_async_callback(monkeypatch):
    """give-up 回调支持协程函数（调度器传的是 async 系统告警发布）。"""
    import app.fetchers.mx.ws as mx_ws

    monkeypatch.setattr(mx_ws, "_reconnect_delay", lambda: 0.01)
    results = []

    async def on_give_up(reason, token_expired=False):
        results.append((reason, token_expired))

    client = MxWsClient(SimpleNamespace(), lambda m: None, on_give_up=on_give_up)

    async def failing_connect():
        raise RuntimeError("down")

    client.connect = failing_connect

    async def scenario():
        await asyncio.wait_for(client.run_forever(), timeout=5)
        # 留出一拍让 _fire_give_up 创建的协程任务跑完
        await asyncio.sleep(0.05)

    asyncio.run(scenario())
    assert client.gave_up is True
    assert len(results) == 1


def test_ws_successful_reconnect_resets_and_keeps_listening(monkeypatch):
    """首连失败后重连成功：恢复重连额度继续监听，不触发放弃回调。"""
    import app.fetchers.mx.ws as mx_ws

    monkeypatch.setattr(mx_ws, "_reconnect_delay", lambda: 0.01)
    give_ups = []
    client = MxWsClient(
        SimpleNamespace(), lambda m: None,
        on_give_up=lambda r, t: give_ups.append((r, t)),
    )
    attempts = {"n": 0}

    async def connect():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("first fail")
        client.connected = True

        async def wait_forever():
            await asyncio.Event().wait()

        client._sio = SimpleNamespace(wait=wait_forever)

    client.connect = connect

    async def scenario():
        task = asyncio.create_task(client.run_forever())
        await asyncio.sleep(0.2)
        assert attempts["n"] == 2
        assert client.gave_up is False
        assert give_ups == []
        assert client.connected is True
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())


def test_ws_gives_up_when_retry_after_clean_drop_fails(monkeypatch):
    """重连成功后再次断线（wait 正常返回）：仍有一次重连机会；该次失败则放弃。"""
    import app.fetchers.mx.ws as mx_ws

    monkeypatch.setattr(mx_ws, "_reconnect_delay", lambda: 0.01)
    give_ups = []
    client = MxWsClient(
        SimpleNamespace(), lambda m: None,
        on_give_up=lambda r, t: give_ups.append((r, t)),
    )
    attempts = {"n": 0}

    async def connect():
        attempts["n"] += 1
        if attempts["n"] == 1:
            async def wait_once():
                pass  # wait() 立即返回 = 服务端正常断开

            client._sio = SimpleNamespace(wait=wait_once)
        else:
            raise RuntimeError("reconnect refused")

    client.connect = connect
    asyncio.run(asyncio.wait_for(client.run_forever(), timeout=5))

    assert attempts["n"] == 2
    assert client.gave_up is True
    assert give_ups and give_ups[0][1] is False and "reconnect refused" in give_ups[0][0]


def test_ws_manual_disconnect_no_give_up(monkeypatch):
    """等待重连窗口内管理员手动断开：正常退出，不触发放弃回调。"""
    import app.fetchers.mx.ws as mx_ws

    give_ups = []
    client = MxWsClient(
        SimpleNamespace(), lambda m: None,
        on_give_up=lambda r, t: give_ups.append((r, t)),
    )

    async def failing_connect():
        raise RuntimeError("down")

    client.connect = failing_connect

    async def fake_sleep(seconds):
        # 首次进入重连等待窗口时模拟管理员手动断开
        await client.stop()

    monkeypatch.setattr(mx_ws.asyncio, "sleep", fake_sleep)
    asyncio.run(asyncio.wait_for(client.run_forever(), timeout=5))

    assert client.gave_up is False
    assert give_ups == []
    assert client.manually_stopped is True
    assert client.running is False


def test_ws_stop_aborts_like_tab_close():
    """退出/停用必须模拟「直接关标签页」：不发任何优雅关闭包，直接掐断底层连接。"""
    class FakeHttp:
        def __init__(self):
            self.closed = False

        async def close(self):
            self.closed = True

    class FakeEio:
        def __init__(self):
            self.http = FakeHttp()

    class FakeSio:
        def __init__(self):
            self.eio = FakeEio()
            self.disconnect_called = False

        async def disconnect(self):
            self.disconnect_called = True
            raise AssertionError("退出不得走优雅断开（不应调用 sio.disconnect）")

    client = MxWsClient(SimpleNamespace(), lambda m: None)
    sio = FakeSio()
    client._sio = sio
    client.connected = True

    asyncio.run(client.stop())

    assert sio.eio.http.closed is True
    assert sio.disconnect_called is False
    assert client.manually_stopped is True
    assert client.connected is False
    assert client._sio is None


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


def test_sync_rooms_reuses_client_until_stop(monkeypatch):
    """房间同步必须复用同一客户端（每次同步新建 TLS 连接是可聚合计数的机器
    信号），stop 时统一关闭。"""
    db = make_db()
    service = MXRoomSyncService(MxConfig(token="t"), db)

    from app.fetchers.mx.client import MXClient

    created = []
    orig_init = MXClient.__init__

    def counting_init(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        created.append(self)

    monkeypatch.setattr(MXClient, "__init__", counting_init)
    monkeypatch.setattr(MXClient, "get_rooms", lambda self: [{"id": 1, "title": "r"}])

    service._sync_rooms_blocking()
    service._sync_rooms_blocking()
    assert len(created) == 1
    assert db.get_kol_by_external("mx", "1") is not None

    closed = []
    monkeypatch.setattr(MXClient, "close", lambda self: closed.append(True))
    service.stop()
    assert closed == [True]


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

    def room_view(self, room_id):
        pass

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

        def room_view(self, room_id):
            pass

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
        def room_view(self, room_id):
            pass

        def get_room_history(self, room_id, msg_id=0, limit=50):
            calls.append(msg_id)
            if msg_id == 0:
                return [msg(5, "m5"), msg(4, "m4")]
            return [msg(4, "m4")]  # 游标 4 → 仍返回 4，不前移

    fetcher.mx_client = Stalled()
    posts = fetcher.fetch(kol)
    assert len(calls) <= 3  # 首页 + 一次追平即停
    assert {p.external_id for p in posts} == {"5", "4"}


# ---- 进房上报（对齐官方「打开房间」行为链） ----

def test_fetch_reports_room_view_before_history():
    """拉取消息前必须先发一次 room/view 进房上报（官方每次打开房间都先发）。"""
    db = make_db()
    kol = make_kol(db)
    fetcher = make_fetcher(db, page_size=50)
    calls = []

    class Fake:
        def room_view(self, room_id):
            calls.append(("view", room_id))

        def get_room_history(self, room_id, msg_id=0, limit=50):
            calls.append(("history", room_id))
            return [msg(2, "m2"), msg(1, "m1")]

    fetcher.mx_client = Fake()
    posts = fetcher.fetch(kol)
    assert calls == [("view", 101), ("history", 101)]
    assert {p.external_id for p in posts} == {"2", "1"}


def test_fetch_survives_room_view_failure():
    """进房上报失败只记日志，不能阻断消息拉取。"""
    db = make_db()
    kol = make_kol(db)
    fetcher = make_fetcher(db, page_size=50)

    class Fake:
        def room_view(self, room_id):
            raise RuntimeError("view failed")

        def get_room_history(self, room_id, msg_id=0, limit=50):
            return [msg(3, "m3")]

    fetcher.mx_client = Fake()
    assert {p.external_id for p in fetcher.fetch(kol)} == {"3"}


# ---- 配置热加载 ----

async def _noop_async_zero():
    """替代 sync_rooms 的空实现：返回 0 个房间。"""
    return 0


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


def test_mx_token_updated_at_recorded_only_on_change(monkeypatch):
    """MX 设置页展示的 Token 更新时间：仅 token 实际变化才刷新，其余字段保存不影响。"""
    import time as time_mod

    from fastapi.testclient import TestClient

    from app.config import Config
    from app.main import create_app

    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("CONFIG_PATH", str(Path(tmp) / "config.yaml"))

    clock = {"now": 1_700_000_000}
    monkeypatch.setattr(time_mod, "time", lambda: clock["now"])

    app = create_app(config=Config(), db_path=Path(tmp) / "t.db")
    client = TestClient(app)
    db = client.app.state.db

    code = "TESTMXT1"
    db.add_register_code(code)
    data = client.post(
        "/api/auth/register",
        json={"username": "mxtokadmin", "password": "secret123", "code": code},
    ).json()
    db.update_user(data["user"]["id"], is_admin=True)
    headers = {"Authorization": f"Bearer {data['token']}"}

    def get_config():
        return client.get("/api/admin/sources/mx", headers=headers).json()

    assert get_config()["token_updated_at"] == ""

    clock["now"] = 1_700_000_100
    client.put(
        "/api/admin/sources/mx",
        json={"enabled": False, "ws_enabled": False, "token": "tok-1"},
        headers=headers,
    )
    assert get_config()["token_updated_at"] == "1700000100"

    # 只调其他字段、token 未变 → 时间不刷新
    clock["now"] = 1_700_000_200
    client.put(
        "/api/admin/sources/mx",
        json={"token": "tok-1", "page_size": 66},
        headers=headers,
    )
    assert get_config()["token_updated_at"] == "1700000100"

    # token 变化 → 时间刷新
    clock["now"] = 1_700_000_300
    client.put(
        "/api/admin/sources/mx",
        json={"token": "tok-2"},
        headers=headers,
    )
    assert get_config()["token_updated_at"] == "1700000300"


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


# ---- TOKEN 过期：连接被拒不重试，直接放弃并标记 ----

def test_ws_token_expired_gives_up_immediately_without_retry(monkeypatch):
    """连接阶段被拒且像 TOKEN 过期：不等待不重试，立即放弃并回调 token_expired=True。"""
    import app.fetchers.mx.ws as mx_ws

    monkeypatch.setattr(mx_ws, "_reconnect_delay", lambda: 0.01)
    give_ups = []
    client = MxWsClient(
        SimpleNamespace(), lambda m: None,
        on_give_up=lambda r, t: give_ups.append((r, t)),
    )
    attempts = {"n": 0}

    async def failing_connect():
        attempts["n"] += 1
        raise RuntimeError("Unexpected status code 401 in server response")

    client.connect = failing_connect
    asyncio.run(asyncio.wait_for(client.run_forever(), timeout=5))

    assert attempts["n"] == 1  # TOKEN 过期绝不重试
    assert client.gave_up is True
    assert give_ups and give_ups[0][1] is True


def test_ws_non_auth_connect_error_still_retries_once(monkeypatch):
    """非鉴权类连接错误（如网络不可达）保持「12 秒后重连一次」策略。"""
    import app.fetchers.mx.ws as mx_ws

    monkeypatch.setattr(mx_ws, "_reconnect_delay", lambda: 0.01)
    give_ups = []
    client = MxWsClient(
        SimpleNamespace(), lambda m: None,
        on_give_up=lambda r, t: give_ups.append((r, t)),
    )
    attempts = {"n": 0}

    async def failing_connect():
        attempts["n"] += 1
        raise RuntimeError("connection refused")

    client.connect = failing_connect
    asyncio.run(asyncio.wait_for(client.run_forever(), timeout=5))

    assert attempts["n"] == 2
    assert give_ups == [("connection refused", False)]


# ---- HTTP 客户端特征修正 ----

class _FakeCffiResponse:
    """curl_cffi Response 的最小鸭子类型。"""

    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeCffiSession:
    """按序返回 payload 的假 curl_cffi Session，记录每次请求供断言。"""

    def __init__(self, payloads):
        self._payloads = payloads
        self.requests = []

    def request(self, method, url, headers=None, data=None, timeout=None):
        self.requests.append(
            {"method": method, "url": url, "headers": headers, "data": data}
        )
        return _FakeCffiResponse(self._payloads[len(self.requests) - 1])


def test_client_headers_look_like_browser():
    """HTTP 请求头必须是 Chrome 同源 XHR 形态；UA/sec-ch-ua 由 impersonate 模板提供，
    _headers 只负责覆盖 XHR 与导航请求的差异项。"""
    from app.fetchers.mx.client import MXClient

    client = MXClient("https://mx.test/business-api/5", "t")
    headers = client._headers()
    assert headers["Origin"] == "https://mx.test"
    assert headers["Referer"] == "https://mx.test/"
    assert headers["token"] == "t" and headers["version"] == "web"
    # accept 为官方实测的 */*（fetch 默认形态），不是 axios 默认值
    assert headers["accept"] == "*/*"
    # 官方前端常驻自定义头：登录前请求即携带、与账号无关（前端写死的渠道标记）
    assert headers["ad"] == "true" and headers["i"] == "qq"
    assert headers["sec-fetch-site"] == "same-origin"
    assert headers["sec-fetch-mode"] == "cors"
    assert headers["sec-fetch-dest"] == "empty"
    # 导航请求特有头必须以 None 标记删除，不能随 impersonate 模板发出
    assert headers["upgrade-insecure-requests"] is None
    assert headers["sec-fetch-user"] is None


def test_get_rooms_single_official_full_pull():
    """房间列表与官方网页端一致：单次 {"pages":1,"limit":1000000} 全量拉取。

    2026-09-02 抓包推翻旧结论：官方冷启动就是单次 limit=1000000（该参数
    无罪，频率才是信号），旧的 100/页翻页反而与官方不符且请求数更多。
    """
    import json as jsonlib

    from app.fetchers.mx.client import MXClient, ROOM_LIST_LIMIT

    rooms = [{"id": i} for i in range(146)]
    session = _FakeCffiSession([{"code": 200, "list": rooms}])
    client = MXClient("https://mx.test/business-api/5", "t", session=session)
    assert client.get_rooms() == rooms

    assert len(session.requests) == 1
    body = jsonlib.loads(session.requests[0]["data"])
    assert body["pages"] == 1 and body["limit"] == ROOM_LIST_LIMIT


def test_token_expired_raises_dedicated_error():
    """TOKEN 过期响应必须抛专用异常，调用方据此停止重试并告警。"""
    import pytest

    from app.fetchers.mx.client import MXClient, MXTokenExpiredError

    session = _FakeCffiSession([{"code": 502, "msg": "token expired"}])
    client = MXClient("https://mx.test/business-api/5", "t", session=session)
    with pytest.raises(MXTokenExpiredError):
        client.get_rooms()


def test_http_wire_persona_matches_ws_persona():
    """真实 curl_cffi 会话发出的线上请求必须与 WS 握手是同一 Chrome 人格：
    UA 逐字节等于 BROWSER_UA、客户端提示一致、无导航残留头、无重复头。
    这是防风控的核心契约：JA3 由 impersonate 保证，此测试锁定头层面。"""
    import http.server
    import threading

    from app.fetchers.mx.client import MXClient
    from app.fetchers.mx.ws import BROWSER_UA, SEC_CH_UA

    captured = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("content-length") or 0))
            keys = [k.lower() for k in self.headers.keys()]
            captured["ua"] = self.headers.get("User-Agent")
            captured["sec_ch_ua"] = self.headers.get("sec-ch-ua")
            captured["accept"] = self.headers.get("accept")
            captured["ad"] = self.headers.get("ad")
            captured["i"] = self.headers.get("i")
            captured["sec_fetch_mode"] = self.headers.get("sec-fetch-mode")
            captured["no_nav"] = (
                "upgrade-insecure-requests" not in keys
                and "sec-fetch-user" not in keys
            )
            captured["no_dups"] = len(keys) == len(set(keys))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"code":200,"list":[{"id":1}]}')

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = MXClient(f"http://127.0.0.1:{port}/business-api/5", "tok")
        rooms = client.get_rooms()
        client.close()
    finally:
        server.shutdown()

    assert rooms == [{"id": 1}]
    assert captured["ua"] == BROWSER_UA
    assert captured["sec_ch_ua"] == SEC_CH_UA
    assert captured["accept"] == "*/*"
    assert captured["sec_fetch_mode"] == "cors"
    assert captured["ad"] == "true" and captured["i"] == "qq"
    assert captured["no_nav"] and captured["no_dups"]


def test_avatar_cache_headers_for_mx_domain():
    """MX 域名图片必须带 MX 站点 Referer，绝不能再带 weibo.com 的假信号。"""
    from app.avatar_cache import headers_for

    headers = headers_for("https://mx.2026.naaifu.cn/uploads/a.png")
    assert headers["User-Agent"].startswith("Mozilla/5.0")
    assert "naaifu.cn" in headers["Referer"]
    assert "weibo.com" not in headers["Referer"]
    # 其他图床行为不变
    assert headers_for("https://wx1.sinaimg.cn/a.jpg")["Referer"] == "https://weibo.com/"


# ---- 客户端人格一致性（HTTP / WS / 常量） ----

def test_ws_handshake_headers_full_chrome_persona():
    """WS 握手头必须与 HTTP 同一 Chrome 人格：UA/客户端提示一致，
    带 Chrome WS 特有的缓存协商头，且任何值都不得暴露 Python 客户端。"""
    from types import SimpleNamespace

    from app.fetchers.mx.ws import (
        ACCEPT_LANGUAGE,
        BROWSER_UA,
        SEC_CH_UA,
        SEC_CH_UA_MOBILE,
        SEC_CH_UA_PLATFORM,
        _browser_handshake_headers,
    )

    config = SimpleNamespace(ws_url="wss://mx.2026.naaifu.cn")
    headers = _browser_handshake_headers(config)
    assert headers["User-Agent"] == BROWSER_UA
    assert headers["Origin"] == "https://mx.2026.naaifu.cn"
    assert headers["sec-ch-ua"] == SEC_CH_UA
    assert headers["sec-ch-ua-mobile"] == SEC_CH_UA_MOBILE
    assert headers["sec-ch-ua-platform"] == SEC_CH_UA_PLATFORM
    assert headers["Accept-Language"] == ACCEPT_LANGUAGE
    # Chrome 的 WebSocket 握手带 Pragma/Cache-Control，也带 sec-fetch-* fetch 元数据
    # （fetch spec：WS 的 mode 为 "websocket"、dest 为空串，同域 site 为 same-origin）
    assert headers["Pragma"] == "no-cache"
    assert headers["sec-fetch-site"] == "same-origin"
    assert headers["sec-fetch-mode"] == "websocket"
    assert headers["sec-fetch-dest"] == "empty"
    assert all("python" not in str(v).lower() for v in headers.values())


def test_persona_constants_are_consistent():
    """UA、sec-ch-ua、impersonate 目标三者的 Chrome 主版本必须一致，
    防止将来只改其中一处造成新的「人格分裂」。"""
    import re

    from app.fetchers.mx.ws import BROWSER_UA, IMPERSONATE_TARGET, SEC_CH_UA

    ua_major = re.search(r"Chrome/(\d+)", BROWSER_UA).group(1)
    hint_majors = set(re.findall(r'v="(\d+)"', SEC_CH_UA))
    assert ua_major in hint_majors
    assert ua_major in IMPERSONATE_TARGET


# ---- 每日运行窗口 ----

def test_mx_daily_windows_within_bounds():
    """三段窗口必须落在各自时段内、互不重叠有序，且开在关之前。"""
    from datetime import date, timedelta

    from app.services.mx_window import generate_mx_daily_windows, in_window

    day = date(2026, 9, 1)
    for _ in range(20):
        windows = generate_mx_daily_windows(day)
        assert len(windows) == 3
        w1, w2, w3 = windows
        # 早市：7:00-8:00 开，11:40-12:00 关
        assert w1[0].hour == 7 and w1[0].minute <= 59
        assert (w1[1].hour, w1[1].minute) >= (11, 40) and w1[1].hour < 12
        # 午后：12:30-12:50 开，16:00-16:30 关
        assert (w2[0].hour, w2[0].minute) >= (12, 30) and w2[0].hour < 13
        assert w2[1].hour == 16 and w2[1].minute <= 29
        # 晚间：19:00-19:30 开，23:30-23:55 关
        assert w3[0].hour == 19 and w3[0].minute <= 29
        assert w3[1].hour == 23 and 30 <= w3[1].minute <= 54
        for start, stop in windows:
            assert start.date() == day and stop.date() == day
            assert start < stop
            assert in_window(start, windows)
            assert in_window(stop - timedelta(seconds=1), windows)
            assert not in_window(stop, windows)
        # 有序且互不重叠
        assert w1[1] <= w2[0] and w2[1] <= w3[0]


def test_arm_windows_disarms_missed_on_restart():
    """重启落在某段窗口内时，该段不武装（不自动续连），后续窗口照常到点开启。"""
    from datetime import date, datetime, time, timedelta

    from app.services.mx_window import CN_TZ, arm_windows, generate_mx_daily_windows

    windows = generate_mx_daily_windows(date(2026, 9, 1))
    # 重启落在第一段窗口内：第一段错过开窗时刻不武装，二三段照常
    mid_w1 = windows[0][0] + timedelta(minutes=10)
    assert arm_windows(windows, mid_w1) == [False, True, True]
    # 重启在所有窗口之前：全部武装（到点自动开启）
    early = datetime.combine(date(2026, 9, 1), time(6, 0), tzinfo=CN_TZ)
    assert arm_windows(windows, early) == [True, True, True]
    # 重启落在第二段窗口内：一、二段都不武装（第二段属中途续连），仅第三段武装
    mid_w2 = windows[1][0] + timedelta(minutes=5)
    assert arm_windows(windows, mid_w2) == [False, False, True]


def test_nightly_force_close_time_within_bounds():
    """晚间断开时刻必须落在 23:30:00-23:55:00 之间（每天随机）。"""
    db = make_db()
    scheduler = _make_scheduler(db)
    scheduler._mx_windows_today()
    fc = scheduler._mx_force_close_at
    assert fc is not None
    assert fc.hour == 23 and 30 <= fc.minute <= 55
    assert not (fc.minute == 55 and fc.second > 0)


def test_nightly_force_close_stops_active_session():
    """到点若仍在线（无论自动/手动登录），晚间强关必须关闭会话。"""
    from datetime import datetime, timedelta

    from app.services.mx_window import CN_TZ

    db = make_db()
    scheduler = _make_scheduler(db)
    scheduler.mx_config = MxConfig(enabled=True, token="t", ws_enabled=False)

    actions = []

    async def fake_ws_control(action, source="manual"):
        # 与真实 mx_ws_control("disconnect") 口径一致：取消 WS 任务并置空
        actions.append((action, source))
        if scheduler._mx_ws_task and not scheduler._mx_ws_task.done():
            scheduler._mx_ws_task.cancel()
        scheduler._mx_ws_task = None
        return "已断开"

    scheduler.mx_ws_control = fake_ws_control
    scheduler._mx_force_close_at = datetime.now(CN_TZ) - timedelta(seconds=1)
    scheduler._mx_force_close_done = False

    async def scenario():
        scheduler._mx_ws_task = asyncio.create_task(asyncio.sleep(3600))  # 模拟会话在线
        await scheduler._mx_maybe_nightly_force_close()

    asyncio.run(scenario())

    assert actions == [("disconnect", "auto")]
    assert scheduler._mx_force_close_done is True
    assert scheduler._mx_window_open is False
    assert scheduler._mx_ws_task is None


def test_nightly_force_close_waits_until_scheduled():
    """未到预约时刻：不关闭、不标记完成。"""
    from datetime import datetime, timedelta

    from app.services.mx_window import CN_TZ

    db = make_db()
    scheduler = _make_scheduler(db)
    scheduler.mx_config = MxConfig(enabled=True, token="t", ws_enabled=False)

    actions = []

    async def fake_ws_control(action, source="manual"):
        actions.append((action, source))
        return "ok"

    scheduler.mx_ws_control = fake_ws_control
    scheduler._mx_force_close_at = datetime.now(CN_TZ) + timedelta(seconds=60)
    scheduler._mx_force_close_done = False

    async def scenario():
        scheduler._mx_ws_task = asyncio.create_task(asyncio.sleep(3600))  # 模拟会话在线
        await scheduler._mx_maybe_nightly_force_close()

    asyncio.run(scenario())

    assert actions == []
    assert scheduler._mx_force_close_done is False
    scheduler._mx_ws_task.cancel()


def test_daily_fallback_slot_inside_window_and_before_close():
    """每日兜底预约时刻必须落在某段窗口内部，且距关窗至少 1 分钟。"""
    from datetime import date, timedelta

    from app.services.mx_window import generate_mx_daily_windows, pick_daily_fallback_slot

    windows = generate_mx_daily_windows(date(2026, 9, 1))
    for _ in range(50):
        slot = pick_daily_fallback_slot(windows)
        assert any(
            start <= slot < stop - timedelta(seconds=60) for start, stop in windows
        )


def test_reconnect_delay_is_random_within_16_36s(monkeypatch):
    """断线重连延时必须取自 16-36 秒随机区间（固定/超短周期重连是机器信号）。"""
    import app.fetchers.mx.ws as mx_ws

    calls = []
    orig_uniform = mx_ws.random.uniform

    def spy(a, b):
        calls.append((a, b))
        return orig_uniform(a, b)

    monkeypatch.setattr(mx_ws.random, "uniform", spy)
    for _ in range(50):
        delay = mx_ws._reconnect_delay()
        assert 16.0 <= delay <= 36.0
    assert calls
    assert {a for a, _ in calls} == {16.0}
    assert {b for _, b in calls} == {36.0}


# ---- 系统通知 KOL：报错统一发布 + 节流 + TOKEN 熔断/时效 ----

def test_publish_mx_error_creates_system_kol_and_throttles():
    """MX 报错走「系统通知」KOL 发布；同 key 30 分钟内只发一条。"""
    from app.scheduler import Scheduler

    db = make_db()
    scheduler = _make_scheduler(db)
    scheduler.publish_mx_error("test_err", "测试告警", "第一条")
    scheduler.publish_mx_error("test_err", "测试告警", "第二条（应被节流）")

    kol = db.get_kol_by_external("system", "system_alert")
    assert kol is not None and kol["name"] == "系统通知"
    rows = db._rows("SELECT COUNT(*) AS c FROM posts WHERE kol_id = ?", (kol["id"],))
    assert rows[0]["c"] == 1
    scheduler.stop()


def test_publish_mx_error_token_expired_sets_circuit_breaker():
    """key=token_expired 的报错必须置 TOKEN 熔断标记。"""
    from app.scheduler import Scheduler

    db = make_db()
    scheduler = _make_scheduler(db)
    assert scheduler._mx_token_expired is False
    scheduler.publish_mx_error("token_expired", "MX TOKEN 已过期", "请更换")
    assert scheduler._mx_token_expired is True
    scheduler.stop()


def test_token_age_reminder_after_two_days():
    """TOKEN 超过 2 天 → 系统通知 KOL 提醒更换，且节流期内不重复提醒。"""
    import time as timelib

    from app.scheduler import Scheduler

    db = make_db()
    scheduler = _make_scheduler(db)

    # 无记录：首次只落基准，不发提醒
    scheduler._mx_check_token_age()
    kol = db.get_kol_by_external("system", "system_alert")
    assert kol is None

    # 回填 3 天前的 TOKEN 起用时间：应发提醒
    db.set_setting("mx_token_updated_at", str(int(timelib.time()) - 3 * 86400))
    scheduler._mx_check_token_age()
    kol = db.get_kol_by_external("system", "system_alert")
    assert kol is not None
    rows = db._rows("SELECT COUNT(*) AS c FROM posts WHERE kol_id = ?", (kol["id"],))
    assert rows[0]["c"] == 1

    # 节流期内再检查：不重复发
    scheduler._mx_check_token_age()
    rows = db._rows("SELECT COUNT(*) AS c FROM posts WHERE kol_id = ?", (kol["id"],))
    assert rows[0]["c"] == 1
    scheduler.stop()


# ---- 房间列表同步：开窗触发（2026-09-02 起不再有后台周期同步） ----

def test_room_sync_service_has_no_periodic_loop():
    """房间同步由开窗动作触发（与官方「打开网页必拉一次」一致），无后台周期任务。"""
    from app.services.mx_sync import MXRoomSyncService

    assert not hasattr(MXRoomSyncService, "start_periodic_sync")


def test_session_start_pulls_room_list_once(monkeypatch):
    """开窗会话启动必须像真人打开网页：先发官方启动序列，再拉一次房间列表。"""
    db = make_db()
    scheduler = _make_scheduler(db)
    scheduler.mx_config = MxConfig(enabled=True, token="t", ws_enabled=False)

    service = MXRoomSyncService(MxConfig(token="t"), db)
    calls = []

    def fake_boot():
        calls.append("boot")

    async def fake_sync():
        calls.append("sync")

    monkeypatch.setattr(service, "boot_sequence", fake_boot)
    monkeypatch.setattr(service, "sync_rooms", fake_sync)
    scheduler._mx_sync_service = service

    asyncio.run(scheduler._mx_session_start())
    assert calls == ["boot", "sync"]


def test_session_start_skips_room_sync_when_token_expired():
    """TOKEN 熔断时开窗不得触发房间同步。"""
    db = make_db()
    scheduler = _make_scheduler(db)
    scheduler.mx_config = MxConfig(enabled=True, token="t", ws_enabled=False)
    scheduler._mx_token_expired = True

    service = MXRoomSyncService(MxConfig(token="t"), db)

    def _must_not_run():
        raise AssertionError("TOKEN 过期时不应触发房间同步")

    service.sync_rooms = _must_not_run
    scheduler._mx_sync_service = service

    asyncio.run(scheduler._mx_session_start())


def test_master_boot_endpoints_wire_format():
    """官方冷启动序列的只读端点：master-api 前缀、请求体、notice 的 GET+query 形态。"""
    import json as jsonlib

    from app.fetchers.mx.client import MXClient

    ok = {"code": 200, "msg": "success"}
    session = _FakeCffiSession([ok] * 4 + [{"code": 200, "msg": "success", "list": []}])
    client = MXClient("https://mx.test/business-api/5", "tok", session=session)

    client.user_info()
    client.system_config()
    client.msg_tip()
    client.room_grouplist()
    client.master_notice()

    assert len(session.requests) == 5
    r_user, r_config, r_tip, r_group, r_notice = session.requests
    assert r_user["url"] == "https://mx.test/master-api/api/user/info"
    assert jsonlib.loads(r_user["data"])["device"] == "web-browser"
    assert r_config["url"] == "https://mx.test/master-api/api/system/config"
    assert jsonlib.loads(r_config["data"])["tt"] > 0
    assert r_tip["url"] == "https://mx.test/business-api/5/api/msg/tip"
    assert r_group["url"] == "https://mx.test/master-api/api/room/grouplist"
    assert r_notice["method"] == "GET"
    assert r_notice["url"].startswith("https://mx.test/master-api/api/notice?tt=")
    assert "token=tok" in r_notice["url"]
    # GET 无 body：不带 Content-Type（与官方 axios 形态一致）
    assert "Content-Type" not in (r_notice["headers"] or {})


def test_boot_sequence_runs_all_steps_and_propagates_token_expiry():
    """启动序列按官方顺序全量执行；TOKEN 过期必须向上抛出（触发熔断）。"""
    import pytest

    from app.fetchers.mx.client import MXTokenExpiredError
    from app.services.mx_sync import MXRoomSyncService

    service = MXRoomSyncService(MxConfig(token="t"), db=None)

    class StubClient:
        def __init__(self):
            self.calls = []

        def user_info(self):
            self.calls.append("user_info")

        def system_config(self):
            self.calls.append("system_config")

        def msg_tip(self):
            self.calls.append("msg_tip")

        def room_grouplist(self):
            self.calls.append("grouplist")

        def master_notice(self):
            self.calls.append("notice")

    stub = StubClient()
    service._client = stub
    service.boot_sequence()
    assert stub.calls == ["user_info", "system_config", "msg_tip", "grouplist", "notice"]

    class ExpiredClient:
        def user_info(self):
            raise MXTokenExpiredError("MX token expired")

        def system_config(self):
            raise AssertionError("TOKEN 过期后不应继续执行后续步骤")

        def msg_tip(self):
            raise AssertionError("TOKEN 过期后不应继续执行后续步骤")

        def room_grouplist(self):
            raise AssertionError("TOKEN 过期后不应继续执行后续步骤")

        def master_notice(self):
            raise AssertionError("TOKEN 过期后不应继续执行后续步骤")

    service._client = ExpiredClient()
    with pytest.raises(MXTokenExpiredError):
        service.boot_sequence()
    # 报告在抛出前已记录失败步骤
    assert service._client is not None


def test_mx_manual_login_reports_each_step(monkeypatch):
    """「登录」按钮：逐接口产出报告（启动序列 → 房间同步 → websocket）。"""
    db = make_db()
    scheduler = _make_scheduler(db)
    scheduler.mx_config = MxConfig(enabled=True, token="t", ws_enabled=False)

    service = MXRoomSyncService(MxConfig(token="t"), db)

    def fake_boot():
        return [
            {"name": "user/info", "ok": True, "detail": "账号 tester", "ms": 3},
            {"name": "system/config", "ok": True, "detail": "ok", "ms": 2},
        ]

    async def fake_sync():
        return 129

    monkeypatch.setattr(service, "boot_sequence", fake_boot)
    monkeypatch.setattr(service, "sync_rooms", fake_sync)
    scheduler._mx_sync_service = service

    report = asyncio.run(scheduler.mx_manual_login())
    assert [s["name"] for s in report["steps"]] == [
        "user/info", "system/config", "room/list", "websocket",
    ]
    assert report["ok"] is True
    assert report["steps"][2]["detail"] == "129 个房间"


def test_mx_manual_login_token_expired_sets_breaker(monkeypatch):
    """TOKEN 过期时「登录」不得继续连接，且必须置熔断标记。"""
    from app.fetchers.mx.client import MXTokenExpiredError

    db = make_db()
    scheduler = _make_scheduler(db)
    scheduler.mx_config = MxConfig(enabled=True, token="t", ws_enabled=False)

    service = MXRoomSyncService(MxConfig(token="t"), db)

    def fake_boot():
        raise MXTokenExpiredError("MX token expired")

    monkeypatch.setattr(service, "boot_sequence", fake_boot)
    scheduler._mx_sync_service = service

    report = asyncio.run(scheduler.mx_manual_login())
    assert report["ok"] is False
    assert scheduler._mx_token_expired is True
    assert any("TOKEN" in s["detail"] for s in report["steps"])


def test_manual_login_report_persists_in_ws_status(monkeypatch):
    """手动登录报告必须写入模块级状态（ws-status 轮询可见，而非只在响应里）。"""
    import app.scheduler as scheduler_mod

    db = make_db()
    scheduler = _make_scheduler(db)
    scheduler.mx_config = MxConfig(enabled=True, token="t", ws_enabled=False)

    service = MXRoomSyncService(MxConfig(token="t"), db)
    monkeypatch.setattr(service, "boot_sequence", lambda: [])
    monkeypatch.setattr(service, "sync_rooms", _noop_async_zero)
    scheduler._mx_sync_service = service

    report = asyncio.run(scheduler.mx_manual_login())
    status = scheduler_mod.get_mx_ws_status()
    assert status["login_report"] is report
    assert status["login_report"]["source"] == "manual"


def test_session_start_records_auto_report(monkeypatch):
    """系统自动 MX 平台登录必须产出逐接口报告（source=auto），而非只有 WS 连接结果。"""
    import app.scheduler as scheduler_mod

    db = make_db()
    scheduler = _make_scheduler(db)
    scheduler.mx_config = MxConfig(enabled=True, token="t", ws_enabled=False)

    service = MXRoomSyncService(MxConfig(token="t"), db)

    def fake_boot():
        return [{"name": "user/info", "ok": True, "detail": "账号 tester", "ms": 3}]

    monkeypatch.setattr(service, "boot_sequence", fake_boot)
    monkeypatch.setattr(service, "sync_rooms", _noop_async_zero)
    scheduler._mx_sync_service = service

    asyncio.run(scheduler._mx_session_start())

    report = scheduler_mod.get_mx_ws_status()["login_report"]
    assert report["source"] == "auto"
    assert report["ok"] is True
    assert [s["name"] for s in report["steps"]] == [
        "user/info", "room/list", "websocket",
    ]


def test_session_start_token_expired_records_failed_report():
    """TOKEN 熔断时系统自动登录：报告如实记录失败原因，且不触发房间同步。"""
    import app.scheduler as scheduler_mod

    db = make_db()
    scheduler = _make_scheduler(db)
    scheduler.mx_config = MxConfig(enabled=True, token="t", ws_enabled=False)
    scheduler._mx_token_expired = True

    service = MXRoomSyncService(MxConfig(token="t"), db)

    def _must_not_run():
        raise AssertionError("TOKEN 过期时不应触发房间同步")

    service.sync_rooms = _must_not_run
    scheduler._mx_sync_service = service

    asyncio.run(scheduler._mx_session_start())

    report = scheduler_mod.get_mx_ws_status()["login_report"]
    assert report["source"] == "auto"
    assert report["ok"] is False
    assert any("TOKEN" in s["detail"] for s in report["steps"])


def test_session_stop_disconnects_as_auto_source():
    """系统自动 MX 平台断开必须带 source=auto，日志不得记成管理员手动。"""
    db = make_db()
    scheduler = _make_scheduler(db)

    calls = []

    async def fake_ws_control(action, source="manual"):
        calls.append((action, source))
        return "已断开"

    scheduler.mx_ws_control = fake_ws_control

    async def scenario():
        scheduler._mx_ws_task = asyncio.create_task(asyncio.sleep(3600))  # 模拟会话在线
        await scheduler._mx_session_stop()

    asyncio.run(scenario())

    assert calls == [("disconnect", "auto")]


def test_auto_session_events_written_to_admin_logs():
    """系统自动 MX 平台登录/断开写入操作日志（user_id=NULL），与管理员手动操作区分。"""
    db = make_db()
    scheduler = _make_scheduler(db)

    scheduler._mx_log_auto_event("mx_auto_login", "第 1 段运行时段到点，系统自动执行 MX 平台登录")

    entry = next(
        r for r in db.list_admin_logs(limit=10) if r["action"] == "mx_auto_login"
    )
    assert entry["user_id"] is None
    assert entry["username"] is None
    assert "系统自动" in entry["detail"]


def test_token_expiry_breaker_also_aborts_ws(monkeypatch):
    """HTTP 先发现 TOKEN 过期时，WS 必须被立即掐断（不能挂在死 token 上）。"""
    db = make_db()
    scheduler = _make_scheduler(db)

    class StubWs:
        def __init__(self):
            self.stopped = False

        async def stop(self, reason: str = "已手动断开"):
            self.stopped = True

    class StubFetcher:
        def __init__(self):
            self.ws_client = StubWs()

    fetcher = StubFetcher()
    scheduler.fetchers["mx"] = fetcher

    async def scenario():
        # 真实应用在 lifespan 事件循环中构造 Scheduler 时即已捕获循环引用
        scheduler._mx_touch_loop()
        scheduler._mx_ws_task = asyncio.create_task(asyncio.sleep(3600))
        # 模拟 HTTP 链路在线程中发现 TOKEN 过期（publish_mx_error 的阻塞调用口径）
        await asyncio.to_thread(
            scheduler.publish_mx_error, "token_expired", "MX TOKEN 已过期", "请更换"
        )
        await asyncio.sleep(0.05)  # 给 WS 掐断任务一拍执行时间
        assert scheduler._mx_token_expired is True
        assert fetcher.ws_client.stopped is True
        assert scheduler._mx_ws_task is None

    asyncio.run(scenario())


def test_mx_config_has_no_fixed_sync_interval_knob():
    """固定间隔配置项已移除，避免留下无效的 UI 输入框/环境变量。"""
    import dataclasses

    from app.config import MxConfig

    assert "sync_interval_hours" not in {f.name for f in dataclasses.fields(MxConfig)}


# ---- 停用房间的实时链路过滤 ----

def test_ws_parse_drops_disabled_room():
    """管理端停用的房间：WS 实时消息在解析层即丢弃（不下载图片/不建帖）。"""
    db = make_db()
    kid = db.add_kol("mx", "房间H", "800")
    fetcher = make_fetcher(db)
    # 启用房间照常解析
    assert fetcher._parse_message_to_post(msg(1, "hello", rid=800)) is not None
    # 停用后：新解析会话（缓存视为已过期）直接丢弃
    db.set_kols_enabled([kid], False)
    fetcher_fresh = make_fetcher(db)
    assert fetcher_fresh._parse_message_to_post(msg(2, "hello", rid=800)) is None


def test_manual_pull_history_ignores_room_disabled():
    """手动拉历史显式传 kol：停用房间仍可补历史（管理员明确动作）。"""
    db = make_db()
    kid = db.add_kol("mx", "房间I", "900")
    db.set_kols_enabled([kid], False)
    fetcher = make_fetcher(db)
    kol = db.get_kol(kid)
    assert fetcher._parse_message_to_post(msg(1, "hello"), kol) is not None


def test_realtime_ingest_skips_disabled_room_immediately():
    """实时入库前按数据库实时状态兜底：停用立即生效，不等房间缓存 TTL。"""
    db = make_db()
    scheduler = _make_scheduler(db)
    scheduler.mx_config = MxConfig(enabled=True, token="t", ws_enabled=False)
    scheduler.fetchers["mx"] = make_fetcher(db)
    kid = db.add_kol("mx", "房间J", "1000")

    async def scenario():
        await scheduler._init_mx()
        callback = scheduler._mx_ws_on_message
        assert callback is not None
        post = Post(platform="mx", kol_id=kid, kol_name="房间J", external_id="m1",
                    title="", content="hi", url="", published_at="2026-01-01 00:00:00",
                    post_type="post", images=[], detail={})
        # 启用房间：正常入库
        await callback(post)
        db.set_kols_enabled([kid], False)
        # 停用后：即使解析层缓存里还是启用态（TTL 内），入库前也会被拦下
        await callback(post)
        rows = db._rows("SELECT COUNT(*) AS c FROM posts WHERE kol_id = ?", (kid,))
        assert rows[0]["c"] == 1

    asyncio.run(scenario())
    scheduler.stop()


def test_realtime_ingest_applies_rule_tags_immediately():
    """MX 实时消息入库前先走本地规则打标（不等 LLM）：话题+股票标签即时可见。"""
    db = make_db()
    scheduler = _make_scheduler(db)
    scheduler.mx_config = MxConfig(enabled=True, token="t", ws_enabled=False)
    scheduler.fetchers["mx"] = make_fetcher(db)
    kid = db.add_kol("mx", "房间K", "1100")
    db.set_stock_aliases([{"alias": "宁王", "stock": "宁德时代"}])

    async def scenario():
        await scheduler._init_mx()
        callback = scheduler._mx_ws_on_message
        post = Post(platform="mx", kol_id=kid, kol_name="房间K", external_id="m1",
                    title="", content="央行宣布降息，宁王可以关注", url="",
                    published_at="2026-01-01 00:00:00", post_type="post", images=[], detail={})
        await callback(post)

    asyncio.run(scenario())
    saved = db.list_posts(platform="mx")[0]
    assert saved["tags"] == ["宏观", "宁德时代"]
    assert saved["llm_tagged"] == 0  # 本地先打，LLM 标记未写
    scheduler.stop()


# ---- 旧版 ws_url 自动迁移 ----

def test_load_config_migrates_legacy_mx_ws_url(tmp_path):
    """旧部署 config.yaml 里的站点根路径 ws_url 加载时迁移为 {api_base} 的 wss 形态。"""
    from app.config import load_config

    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "sources:\n"
        "  mx:\n"
        "    enabled: true\n"
        "    api_base: https://mx.2026.naaifu.cn/business-api/5\n"
        "    ws_url: wss://mx.2026.naaifu.cn\n",
        encoding="utf-8",
    )
    config = load_config(cfg)
    assert config.sources.mx.ws_url == "wss://mx.2026.naaifu.cn/business-api/5"


def test_load_config_keeps_custom_mx_ws_url(tmp_path):
    """已是带路径形态（官方/自定义）的 ws_url 不被迁移覆盖。"""
    from app.config import load_config

    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "sources:\n"
        "  mx:\n"
        "    api_base: https://mx.2026.naaifu.cn/business-api/5\n"
        "    ws_url: wss://mx.2026.naaifu.cn/business-api/5\n",
        encoding="utf-8",
    )
    config = load_config(cfg)
    assert config.sources.mx.ws_url == "wss://mx.2026.naaifu.cn/business-api/5"
