"""MX 平台接入：消息解析兜底、房间同步、广场显隐、配置热加载。"""
import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace

from app.db import DB
from app.fetchers.base import Post
from app.fetchers.mx.fetcher import MxFetcher, looks_like_image_url, normalize_mx_text
from app.fetchers.mx.ws import MxWsClient
from app.plaza import filter_plaza_kol_rows, kol_plaza_hidden


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


def test_text_embedded_file_kv_extracted_as_attachment():
    """text 消息整条是「url=...,fileName=...」键值串（客户端把文件分享序列化成文本）：
    提取为附件、正文合成 [文件] 占位，files 同时合入 detail 供推送渠道渲染。"""
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    raw = {
        "id": 21,
        "rid": 101,
        "msg": '[{"type":"text","msg":"url=https://dpmedia.oss-cn-chengdu.aliyuncs.com/20260829/%E4%B8%AD%E6%8A%A5%E4%BA%A4%E6%B5%81.pdf,fileName=中报交流纪要合集.pdf"}]',
        "createtime": 1700000000000,
    }
    post = fetcher._parse_message_to_post(raw, kol)
    assert post is not None
    assert post.content == "[文件]"
    assert post.detail["files"] == [{
        "url": "https://dpmedia.oss-cn-chengdu.aliyuncs.com/20260829/%E4%B8%AD%E6%8A%A5%E4%BA%A4%E6%B5%81.pdf",
        "name": "中报交流纪要合集.pdf",
    }]


def test_text_embedded_file_share_text_extracted():
    """「分享了一份文件：文件名\\nURL（带签名查询串）」同样提取为附件。"""
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    raw = {
        "id": 22,
        "rid": 101,
        "msg": '[{"type":"text","msg":"分享了一份文件：中报交流纪要合集（陆续补充）-截止20260828.pdf\\n'
               'https://jf119255422.oss-cn-hangzhou.aliyuncs.com/%E4%B8%AD%E6%8A%A5.pdf?Expires=1787950690&OSSAccessKeyId=LTAI&Signature=b1%3D"}]',
        "createtime": 1700000000000,
    }
    post = fetcher._parse_message_to_post(raw, kol)
    assert post is not None
    assert post.content == "[文件]"
    files = post.detail["files"]
    assert len(files) == 1
    assert files[0]["name"] == "中报交流纪要合集（陆续补充）-截止20260828.pdf"
    assert files[0]["url"].endswith("Signature=b1%3D")


def test_text_embedded_file_keeps_other_text():
    """文件分享文本与普通文字混排：正文只留普通文字，附件进 files。"""
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    raw = {
        "id": 23,
        "rid": 101,
        "msg": '[{"type":"text","msg":"看报告"},'
               '{"type":"text","msg":"url=https://x.test/a.pdf,fileName=报告.pdf"}]',
        "createtime": 1700000000000,
    }
    post = fetcher._parse_message_to_post(raw, kol)
    assert post is not None
    assert post.content == "看报告"
    assert post.detail["files"] == [{"url": "https://x.test/a.pdf", "name": "报告.pdf"}]


def test_plain_text_with_url_not_extracted_as_file():
    """普通正文不误伤：url= 缺 fileName、链接单独成行等保持纯文本，不进 files。"""
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    for text in (
        "url=https://x.test/a.pdf",
        "分享了一份文件：报告 https://x.test/a.pdf",
        "推荐看这篇 https://x.test/a.pdf",
    ):
        raw = {
            "id": 24,
            "rid": 101,
            "msg": f'[{{"type":"text","msg":"{text}"}}]',
            "createtime": 1700000000000,
        }
        post = fetcher._parse_message_to_post(raw, kol)
        assert post is not None
        assert post.content == text
        assert "files" not in post.detail


def test_file_message_files_merged_into_detail():
    """type=file 消息的附件同样合入 detail["files"]，纯图片消息不加 files 键。"""
    db = make_db()
    fetcher = make_fetcher(db)
    kol = make_kol(db)
    file_raw = {
        "id": 25,
        "rid": 101,
        "msg": '[{"type":"file","url":"https://img.test/doc.pdf","name":"文档"}]',
        "createtime": 1700000000000,
    }
    post = fetcher._parse_message_to_post(file_raw, kol)
    assert post is not None
    assert post.detail["files"] == [{"url": "https://img.test/doc.pdf", "name": "文档"}]

    pic_raw = {
        "id": 26,
        "rid": 101,
        "msg": '[{"type":"text","msg":"看图"},{"type":"pic","url":"https://img.test/a.jpg"}]',
        "createtime": 1700000000000,
    }
    post = fetcher._parse_message_to_post(pic_raw, kol)
    assert post is not None
    assert "files" not in post.detail


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


def test_normalize_strips_dangling_list_markers():
    """只含列表符号的悬空占位行替换为空行（文件本体是独立 file 消息，占位行
    只会渲染成空列表项；替换而非删除，大V手打的「-」「·」分隔行被清掉后
    上下两段正文不会直接粘连）。"""
    assert normalize_mx_text("文件：\n- \n- ") == "文件：\n\n"
    assert normalize_mx_text("A\n-\nB") == "A\n\nB"
    assert normalize_mx_text("A\n*\n1.\nB") == "A\n\n\nB"
    # 带内容的列表项、水平分隔线、正常引用不动
    assert normalize_mx_text("- 条目内容\n---\n> 引用") == "- 条目内容\n---\n> 引用"
    # 「1. 5倍」数字开头有正文不是悬空序号
    assert normalize_mx_text("涨了\n1. 5倍") == "涨了\n1. 5倍"


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


# ---- WS 重连策略：断线后仅随机重连一次，失败永久放弃 ----

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


def test_get_rooms_single_official_full_pull():
    """房间列表与官方网页端一致：单次 {"pages":1,"limit":1000000} 全量拉取。

    2026-09-02 抓包推翻旧结论：官方冷启动就是单次 limit=1000000（该参数
    无罪，频率才是信号），旧的 100/页翻页反而与官方不符且请求数更多。
    """
    import json as jsonlib

    from app.fetchers.mx.client import ROOM_LIST_LIMIT, MXClient

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
            keys = [k.lower() for k in self.headers]
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

