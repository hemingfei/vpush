"""Approval behavior without an HTTP application or external requests."""
from unittest.mock import Mock

import pytest

from app import kol_requests
from app.db import DB


@pytest.fixture
def approval(tmp_path):
    db = DB(tmp_path / "approval.sqlite")
    admin_id = db.add_user("admin", "hash", is_admin=True)
    requester_id = db.add_user("requester", "hash")
    category_id = db.add_category("Research")
    return db, db.get_user(admin_id), requester_id, category_id


@pytest.mark.parametrize("platform, external_id, resolver", [
    ("xueqiu", "123456", "resolve_profile"),
    ("combination", "ZH123456", "resolve_combination_profile"),
    ("weibo", "123456", "resolve_weibo_profile"),
    ("twitter", "example", "resolve_x_profile"),
    ("zsxq", "123456", "resolve_zsxq_profile"),
])
def test_approval_resolves_profile_and_subscribes(approval, monkeypatch,
                                               platform, external_id, resolver):
    db, admin, requester_id, category_id = approval
    request_id = db.add_kol_request(platform, external_id, requester_id,
                                   "", category_id=category_id)
    profile = Mock(return_value={"name": "Resolved", "screen_name": "Resolved",
                                 "avatar_url": "https://example.com/avatar.png"})
    avatar = Mock(return_value="/avatars/test.png")
    monkeypatch.setattr(kol_requests, resolver, profile)
    monkeypatch.setattr(kol_requests, "cache_avatar", avatar)

    kol = kol_requests.approve_kol_request(db, request_id, admin)

    assert kol["name"] == "Resolved"
    assert kol["category_id"] == category_id
    assert kol["id"] in db.subscribed_kol_ids(requester_id)
    assert db.get_kol_request(request_id)["status"] == "approved"
    profile.assert_called_once()
    avatar.assert_called_once_with(db, kol["id"], "https://example.com/avatar.png")
    with pytest.raises(kol_requests.KolRequestNotFound, match="申请不存在或已处理"):
        kol_requests.approve_kol_request(db, request_id, admin)
    assert profile.call_count == 1


def test_rejection_and_missing_request_use_business_errors(approval):
    db, admin, requester_id, category_id = approval
    request_id = db.add_kol_request("xueqiu", "123456", requester_id,
                                   "Requested", category_id=category_id)
    kol_requests.reject_kol_request(db, request_id, admin)
    assert db.get_kol_request(request_id)["status"] == "rejected"
    assert db.subscribed_kol_ids(requester_id) == set()
    for operation in (kol_requests.approve_kol_request, kol_requests.reject_kol_request):
        for missing_id in (request_id, request_id + 1):
            with pytest.raises(kol_requests.KolRequestNotFound):
                operation(db, missing_id, admin)


def test_invalid_request_remains_pending(approval):
    db, admin, requester_id, category_id = approval
    request_id = db.add_kol_request("xueqiu", "invalid", requester_id,
                                   "Requested", category_id=category_id)
    with pytest.raises(kol_requests.KolRequestError, match="外部ID"):
        kol_requests.approve_kol_request(db, request_id, admin)
    assert db.get_kol_request(request_id)["status"] == "pending"


def test_category_override_validation_and_subscription_failure(approval, monkeypatch):
    db, admin, requester_id, category_id = approval
    request_id = db.add_kol_request("xueqiu", "123456", requester_id,
                                   "Requested", category_id=category_id)
    monkeypatch.setattr(kol_requests, "resolve_profile", lambda *a, **kw: {})
    with pytest.raises(kol_requests.KolRequestError, match="分类不存在"):
        kol_requests.approve_kol_request(db, request_id, admin, category_id=999999)
    assert db.get_kol_request(request_id)["status"] == "pending"
    override = db.add_category("Override")
    monkeypatch.setattr(db, "add_subscription", Mock(side_effect=RuntimeError("offline failure")))
    kol = kol_requests.approve_kol_request(db, request_id, admin, category_id=override)
    assert kol["category_id"] == override
    assert db.get_kol_request(request_id)["status"] == "approved"
