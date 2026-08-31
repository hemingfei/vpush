from datetime import UTC, datetime
from types import SimpleNamespace

from app.knowledge_notify import (
    SETTINGS_LAST_CHECK,
    document_keyword_hit,
    format_digest,
    is_watchable_report_tag,
    maybe_notify_knowledge_keywords,
)
from tests.test_api import make_client, user_headers
from tests.test_scheduler import make_db


def _doc(**kwargs):
    now = datetime.now(UTC).isoformat()
    base = {
        "group_id": "local-cicc-research",
        "media_id": "m1",
        "name": "宁德时代深度：产能与价格",
        "group_name": "中金点睛",
        "abstract": "动力电池需求",
        "abstract_zh": "",
        "tags": ["宁德时代", "中金研报", "公司研究"],
        "downloaded_at": now,
        "sort_date": "2026-08-31",
    }
    base.update(kwargs)
    return base


def test_watchable_tags_skip_library_and_cicc_categories():
    assert is_watchable_report_tag("宁德时代")
    assert is_watchable_report_tag("宏观")
    assert not is_watchable_report_tag("中金研报")
    assert not is_watchable_report_tag("公司研究")
    assert not is_watchable_report_tag("行业研究")
    assert not is_watchable_report_tag("")


def test_document_keyword_hit_title_abstract_and_tags():
    doc = _doc()
    assert document_keyword_hit(["宁德时代"], doc) == ["宁德时代"]
    assert document_keyword_hit(["动力电池"], doc) == ["动力电池"]
    assert document_keyword_hit(["茅台"], doc) == []
    assert document_keyword_hit(["宁德时代", "茅台", "中金点睛"], doc) == ["宁德时代", "中金点睛"]


def test_format_digest_caps_and_extra():
    docs = [_doc(media_id=f"m{i}", name=f"标题{i}") for i in range(3)]
    text = format_digest(docs, extra=2)
    assert "今日研报 5 篇命中关键词" in text
    assert "· 标题0（中金点睛）" in text
    assert "还有 2 篇" in text
    assert "打开研报库查看" in text


def _seed_user_and_doc(db, *, match=True, dnd=False, acl=True, admin=False):
    uid = db.add_user("kwrep", "h")
    db.update_user(
        uid,
        notify_enabled=True,
        keywords_match_reports=match,
        keywords_match_reports_since="2026-01-01T00:00:00+00:00",
        telegram_chat_id="111",
        dnd_start="00:00" if dnd else "",
        dnd_end="23:59" if dnd else "",
        is_admin=admin,
    )
    db.set_user_keywords(uid, ["宁德时代"])
    if acl:
        db.set_ima_kb_acl_for_user(uid, ["local-cicc-research"])
    db.update_ima_document_batch([_doc()], "fp-kw")
    db.set_setting(SETTINGS_LAST_CHECK, "0")
    return uid


def _patch_send(monkeypatch, bucket):
    monkeypatch.setattr(
        "app.knowledge_notify.iter_user_channels",
        lambda *a, **k: ["telegram"],
    )

    class Fake:
        def send_text(self, text, reply_markup=None):
            bucket.append(text)

    monkeypatch.setattr(
        "app.knowledge_notify.build_channel_notifier",
        lambda *a, **k: Fake(),
    )
    monkeypatch.setattr(
        "httpx.Client",
        lambda **k: SimpleNamespace(close=lambda: None),
    )


def test_notify_sends_one_digest_and_is_idempotent(monkeypatch):
    db = make_db()
    _seed_user_and_doc(db)
    sent = []
    _patch_send(monkeypatch, sent)
    cfg = SimpleNamespace()
    assert maybe_notify_knowledge_keywords(db, cfg, now=2_000_000_000) == 1
    assert len(sent) == 1
    assert "宁德时代" in sent[0] or "今日研报 1 篇" in sent[0]
    db.set_setting(SETTINGS_LAST_CHECK, "0")
    assert maybe_notify_knowledge_keywords(db, cfg, now=2_000_000_100) == 0
    assert len(sent) == 1


def test_notify_skips_without_acl(monkeypatch):
    db = make_db()
    _seed_user_and_doc(db, acl=False)
    sent = []
    _patch_send(monkeypatch, sent)
    assert maybe_notify_knowledge_keywords(db, SimpleNamespace(), now=2_000_000_000) == 0
    assert sent == []


def test_notify_skips_dnd_and_retries_later(monkeypatch):
    db = make_db()
    uid = _seed_user_and_doc(db, dnd=True)
    sent = []
    _patch_send(monkeypatch, sent)
    assert maybe_notify_knowledge_keywords(db, SimpleNamespace(), now=2_000_000_000) == 0
    assert sent == []
    db.update_user(uid, dnd_start="", dnd_end="")
    db.set_setting(SETTINGS_LAST_CHECK, "0")
    assert maybe_notify_knowledge_keywords(db, SimpleNamespace(), now=2_000_000_200) == 1
    assert len(sent) == 1


def test_admin_can_match_without_acl(monkeypatch):
    db = make_db()
    _seed_user_and_doc(db, acl=False, admin=True)
    sent = []
    _patch_send(monkeypatch, sent)
    assert maybe_notify_knowledge_keywords(db, SimpleNamespace(), now=2_000_000_000) == 1
    assert sent


def test_keywords_match_reports_api():
    client = make_client()
    headers = user_headers(client, "kw_report_user")
    me = client.get("/api/me", headers=headers).json()
    assert me["keywords_match_reports"] is False
    resp = client.put("/api/me", headers=headers, json={"keywords_match_reports": True})
    assert resp.status_code == 200
    me = client.get("/api/me", headers=headers).json()
    assert me["keywords_match_reports"] is True
    user = client.app.state.db.get_user(me["id"])
    assert user["keywords_match_reports_since"]
