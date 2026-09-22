"""ARM lab ops phase 2: requeue safety, confirm/limit caps, redaction, mocked jobs."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

OPS_DIR = Path(__file__).resolve().parent.parent / "arm-lab-ops"
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(OPS_DIR))

from ops_actions import (  # noqa: E402
    ActionError,
    cicc_sync,
    clamp_sync_limit,
    ima_sync,
    normalize_ima_group,
    requeue_failed,
    require_confirm,
    run_subprocess_job,
    safe_relpath,
)
from ops_app import create_app  # noqa: E402
from ops_status import (  # noqa: E402
    cache_waterline,
    collect_status,
    parse_cicc_sync_log,
    parse_ima_sync_log,
    puller_upload_counts,
    redact,
)


@pytest.fixture
def lab_env(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    secrets = tmp_path / "secrets"
    scripts = tmp_path / "scripts"
    cache.mkdir()
    (cache / "staging").mkdir()
    (cache / "hot").mkdir()
    (cache / "failed").mkdir()
    (cache / "logs").mkdir()
    (cache / "manifest").mkdir()
    secrets.mkdir()
    scripts.mkdir()
    (scripts / "ima_arm_lab_sync.py").write_text("# fake ima\n", encoding="utf-8")
    (scripts / "cicc_report_collector.py").write_text("# fake cicc\n", encoding="utf-8")
    secrets.joinpath("ima-pure.json").write_text(
        json.dumps({"uid": "user-123456", "refresh_token": "super-secret-refresh"}),
        encoding="utf-8",
    )
    secrets.joinpath("115-cookies.txt").write_text("UID=cookie-secret; CID=x", encoding="utf-8")
    secrets.joinpath("cicc-cookies.txt").write_text("Cookie: secret-cicc", encoding="utf-8")
    monkeypatch.setenv("ARM_OPS_PASSWORD", "lab-secret")
    monkeypatch.setenv("CACHE_ROOT", str(cache))
    monkeypatch.setenv("P115_COOKIES_FILE", str(secrets / "115-cookies.txt"))
    monkeypatch.setenv("IMA_PURE_SECRETS_FILE", str(secrets / "ima-pure.json"))
    monkeypatch.setenv("VPUSH_CICC_COOKIE_FILE", str(secrets / "cicc-cookies.txt"))
    monkeypatch.setenv("VPUSH_SCRIPTS_ROOT", str(scripts))
    monkeypatch.setenv("VPUSH_SRC_ROOT", str(tmp_path))
    monkeypatch.setenv("OPENLIST_PUBLIC_URL", "http://127.0.0.1:5244/lab-hot")
    monkeypatch.delenv("PULLER_HEALTH_URL", raising=False)
    monkeypatch.setenv("PULLER_HEALTH_FILE", str(cache / "logs" / "health.json"))
    monkeypatch.delenv("VPUSH_ARM_MIDDLEWARE", raising=False)
    return cache, secrets, scripts


@pytest.fixture
def client(lab_env):
    return TestClient(create_app())


def _login(client: TestClient, password: str = "lab-secret"):
    return client.post("/login", data={"password": password}, follow_redirects=False)


def test_safe_relpath_rejects_escape():
    assert safe_relpath("local/ima/a.pdf").as_posix() == "local/ima/a.pdf"
    assert safe_relpath("./local/foo.pdf").as_posix() == "local/foo.pdf"
    with pytest.raises(ActionError, match="relative"):
        safe_relpath("/etc/passwd")
    with pytest.raises(ActionError, match="escapes"):
        safe_relpath("../staging/x.pdf")
    with pytest.raises(ActionError, match="escapes"):
        safe_relpath("foo/../../etc/passwd")
    with pytest.raises(ActionError, match="relative"):
        safe_relpath("~/secrets")
    with pytest.raises(ActionError, match="invalid"):
        safe_relpath("foo\x00bar")
    with pytest.raises(ActionError, match="path required"):
        safe_relpath("   ")


def test_confirm_and_limit_caps():
    with pytest.raises(ActionError, match="confirm required"):
        require_confirm({})
    with pytest.raises(ActionError, match="confirm required"):
        require_confirm({"confirm": "true"})
    require_confirm({"confirm": True})
    assert clamp_sync_limit(None) == 3
    assert clamp_sync_limit(1) == 1
    assert clamp_sync_limit(99) == 5
    assert clamp_sync_limit(0) == 1
    with pytest.raises(ActionError, match="integer"):
        clamp_sync_limit("nope")
    assert normalize_ima_group("legacy") == "legacy"
    assert normalize_ima_group("7479082602225992") == "7479082602225992"
    with pytest.raises(ActionError, match="not allowed"):
        normalize_ima_group("not-a-group")


def test_requeue_moves_and_strips_sidecar(lab_env):
    cache, _secrets, _scripts = lab_env
    rel = Path("local/ima/legacy/2026/09/19/doc.pdf")
    src = cache / "failed" / rel
    src.parent.mkdir(parents=True)
    src.write_bytes(b"%PDF-fail")
    sidecar = src.with_name(src.name + ".retry.json")
    sidecar.write_text(json.dumps({"attempts": 3, "last_error": "empty filesha1"}), encoding="utf-8")

    result = requeue_failed({"confirm": True, "paths": [rel.as_posix()]}, root=cache)
    assert result["ok"] is True
    assert result["count"] == 1
    dest = cache / "staging" / rel
    assert dest.is_file()
    assert dest.read_bytes() == b"%PDF-fail"
    assert not src.exists()
    assert not sidecar.exists()
    audit = (cache / "logs" / "ops-audit.jsonl").read_text(encoding="utf-8")
    assert "requeue" in audit
    assert "empty filesha1" not in audit


def test_requeue_rejects_escape_and_requires_confirm(lab_env):
    cache, _secrets, _scripts = lab_env
    with pytest.raises(ActionError, match="confirm required"):
        requeue_failed({"paths": ["local/a.pdf"]}, root=cache)
    (cache / "failed" / "keep.pdf").write_bytes(b"x")
    result = requeue_failed({"confirm": True, "paths": ["../staging/x", "/etc/passwd"]}, root=cache)
    assert result["count"] == 0
    assert result["skipped"]
    assert (cache / "failed" / "keep.pdf").is_file()
    assert list((cache / "staging").iterdir()) == []


def test_requeue_all_caps_and_skips_existing(lab_env):
    cache, _secrets, _scripts = lab_env
    src = cache / "failed" / "local" / "a.pdf"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"new")
    dest = cache / "staging" / "local" / "a.pdf"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"old")
    other = cache / "failed" / "local" / "b.pdf"
    other.write_bytes(b"b")
    result = requeue_failed({"confirm": True, "all": True}, root=cache)
    assert "local/b.pdf" in result["moved"]
    assert any(row["reason"] == "staging dest exists" for row in result["skipped"])
    assert dest.read_bytes() == b"old"


def test_parse_ima_sync_log_redacts_and_groups(tmp_path):
    log = tmp_path / "ima-lab-sync-20260919.log"
    log.write_text(
        "\n".join(
            [
                "start group=legacy",
                "SYNC media_id=pdf_1 title=a dest=/data/vpush-ima-cache/staging/local/ima/legacy/a.pdf",
                "SKIP exists media_id=pdf_2 dest=/tmp/x",
                "apply downloaded=1 skipped=1 failed=0（115 仍由 puller_loop 上传）",
                "start group=7479082602225992",
                "FAIL media_id=pdf_x error=UID=cookie-secret refresh_token=super-secret-refresh",
                "apply downloaded=0 skipped=0 failed=1（115 仍由 puller_loop 上传）",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    summary = parse_ima_sync_log(log)
    assert summary["groups"]["legacy"] == {"downloaded": 1, "skipped": 1, "failed": 0}
    assert summary["groups"]["7479082602225992"] == {"downloaded": 0, "skipped": 0, "failed": 1}
    assert summary["totals"]["failed"] == 1
    assert summary["last_error"]
    dumped = json.dumps(summary)
    assert "cookie-secret" not in dumped
    assert "super-secret-refresh" not in dumped
    assert "UID=<redacted>" in dumped


def test_parse_ima_sync_log_clears_last_error_after_later_success(tmp_path):
    log = tmp_path / "ima-lab-sync-20260920.log"
    log.write_text(
        "\n".join(
            [
                "lab sync 失败: IMA list failed code=30021",
                "=== sequential apply start ===",
                "group=legacy",
                "apply downloaded=1 skipped=0 failed=0",
                "=== sequential apply end rc=0 ===",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    summary = parse_ima_sync_log(log)
    assert summary["totals"]["downloaded"] == 1
    assert summary["last_error"] is None


def test_parse_cicc_sync_log_clears_last_error_after_rc0(tmp_path):
    log = tmp_path / "cicc-host-sync-20260920.log"
    log.write_text(
        "start 2026-09-20T12:00:00+08:00 days=3 dry_run=0\n"
        "lab sync 失败: timeout\n"
        "done rc=0 2026-09-20T12:01:00+08:00\n",
        encoding="utf-8",
    )
    summary = parse_cicc_sync_log(log)
    assert summary["returncode"] == 0
    assert summary["last_error"] is None


def test_parse_cicc_host_sync_log(tmp_path):
    log = tmp_path / "cicc-host-sync-20260920.log"
    log.write_text(
        "start 2026-09-20T12:00:00+08:00 days=3 dry_run=0\n"
        "downloaded ok UID=cookie-secret\n"
        "done rc=0 2026-09-20T12:01:00+08:00\n",
        encoding="utf-8",
    )
    summary = parse_cicc_sync_log(log)
    assert summary["days"] == 3
    assert summary["dry_run"] is False
    assert summary["returncode"] == 0
    assert "cookie-secret" not in json.dumps(summary)


def test_status_includes_sync_waterline_failed_queue(lab_env):
    cache, _secrets, _scripts = lab_env
    (cache / "logs" / "ima-lab-sync-20260919.log").write_text(
        "group=legacy\napply downloaded=2 skipped=1 failed=0\nFAIL boom UID=cookie-secret\n",
        encoding="utf-8",
    )
    failed = cache / "failed" / "local" / "miss.pdf"
    failed.parent.mkdir(parents=True)
    failed.write_bytes(b"xx")
    (cache / "staging" / "a.pdf").write_bytes(b"%PDF")
    (cache / "manifest" / "uploads.jsonl").write_text(
        json.dumps({"ok": True, "relpath": "a.pdf"}) + "\n" + json.dumps({"ok": False, "relpath": "b.pdf"}) + "\n",
        encoding="utf-8",
    )
    payload = collect_status()
    dumped = json.dumps(payload)
    assert "cookie-secret" not in dumped
    assert "super-secret-refresh" not in dumped
    assert payload["sync"]["totals"]["downloaded"] == 2
    assert payload["failed_queue"]["count"] == 1
    assert payload["failed_queue"]["items"][0]["path"] == "local/miss.pdf"
    assert payload["cache"]["waterline"]["warn_gb"] == 30.0
    assert payload["cache"]["waterline"]["force_gb"] == 35.0
    assert payload["puller"]["uploads"]["ok"] == 1
    assert payload["puller"]["uploads"]["fail"] == 1
    assert payload["cicc"]["present"] is True
    assert payload["roles"]["vpush_link"] == "http_pull"
    assert payload["roles"]["storage"] == "storage_then_115"
    assert [row["id"] for row in payload["backups"]] == ["storage", "p115"]
    assert payload["backups"][0]["priority"] == 1
    assert payload["backups"][1]["priority"] == 2
    assert payload["openlist"]["role"] == "browse"
    assert payload["puller"]["policy"]["keep_hot"] is True
    assert "export" in payload
    assert "secret-cicc" not in dumped


def test_waterline_levels(lab_env, monkeypatch):
    cache, _secrets, _scripts = lab_env
    monkeypatch.setenv("CACHE_WARN_GB", "0.00000001")
    monkeypatch.setenv("CACHE_FORCE_GB", "0.00000002")
    (cache / "staging" / "big.bin").write_bytes(b"x" * 80)
    water = cache_waterline(cache)
    assert water["level"] in {"warn", "force"}
    assert water["used_bytes"] >= 80


def test_api_requeue_and_confirm(client, lab_env):
    cache, _secrets, _scripts = lab_env
    src = cache / "failed" / "x.pdf"
    src.write_bytes(b"pdf")
    assert _login(client).status_code == 303
    denied = client.post("/api/failed/requeue", json={"paths": ["x.pdf"]})
    assert denied.status_code == 400
    assert denied.json()["error"] == "confirm required"
    ok = client.post("/api/failed/requeue", json={"confirm": True, "paths": ["x.pdf"]})
    assert ok.status_code == 200
    assert ok.json()["count"] == 1
    assert (cache / "staging" / "x.pdf").is_file()


class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_ima_sync_refuses_dual_collect(lab_env):
    with pytest.raises(ActionError, match="勿在此双采"):
        ima_sync({"confirm": True, "limit": 2, "group": "legacy"}, dry_run=False)
    with pytest.raises(ActionError, match="勿在此双采"):
        ima_sync({"limit": 2, "group": "legacy"}, dry_run=True)


def test_cicc_missing_cookie_is_400(lab_env, monkeypatch):
    _cache, secrets, _scripts = lab_env
    secrets.joinpath("cicc-cookies.txt").unlink()
    with pytest.raises(ActionError, match="cookie file missing"):
        cicc_sync({"confirm": True, "limit": 2}, dry_run=False)


def test_cicc_apply_mocked(lab_env, monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["env"] = kwargs.get("env") or {}
        seen["timeout"] = kwargs.get("timeout")
        return _Proc(0, "apply downloaded=1 skipped=0 failed=0\n", "")

    monkeypatch.setattr("ops_actions.subprocess.run", fake_run)
    result = cicc_sync({"confirm": True, "days": 3}, dry_run=False)
    assert result["ok"] is True
    assert result["days"] == 3
    assert "--cookie-file" not in seen["argv"]
    assert seen["env"]["VPUSH_CICC_COOKIE_FILE"].endswith("cicc-cookies.txt")
    assert "--arm-middleware" in seen["argv"]
    assert "--days" in seen["argv"]
    assert "3" in seen["argv"]
    assert "--dry-run" not in seen["argv"]
    assert "cicc_report_collector.py" in " ".join(seen["argv"])
    assert seen["timeout"] == 21600


def test_api_sync_endpoints_mocked(client, lab_env, monkeypatch):
    def fake_run(argv, **kwargs):
        return _Proc(0, "WOULD SYNC title=demo refresh_token=super-secret-refresh\n", "")

    monkeypatch.setattr("ops_actions.subprocess.run", fake_run)
    assert _login(client).status_code == 303
    refused = client.post("/api/sync/ima/dry-run", json={"limit": 2, "group": "legacy"})
    assert refused.status_code == 409
    dry = client.post("/api/sync/cicc/dry-run", json={"days": 2})
    assert dry.status_code == 200
    body = dry.json()
    assert body["ok"] is True
    assert "super-secret-refresh" not in json.dumps(body)
    denied = client.post("/api/sync/cicc/apply", json={"days": 2})
    assert denied.status_code == 400
    apply = client.post(
        "/api/sync/cicc/apply",
        json={"confirm": True, "days": 2},
    )
    assert apply.status_code == 200
    status = client.get("/api/status").json()
    assert status["last_job"]["action"] in {"cicc-dry-run", "cicc-apply"}
    assert "super-secret-refresh" not in json.dumps(status)


def test_subprocess_timeout_and_lock(lab_env, monkeypatch):
    cache, _secrets, _scripts = lab_env

    def boom(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1, output="UID=cookie-secret")

    monkeypatch.setattr("ops_actions.subprocess.run", boom)
    row = run_subprocess_job("ima-dry-run", [sys.executable, str(SCRIPTS_DIR / "ima_arm_lab_sync.py"), "--enable"])
    assert row["timeout"] is True
    assert "cookie-secret" not in json.dumps(row)
    assert (cache / "logs" / "ops-last-job.json").is_file()


def test_scripts_root_prefers_env(lab_env):
    from ops_settings import scripts_root

    assert scripts_root().name == "scripts"


def test_puller_counts_from_heartbeat(lab_env):
    cache, _secrets, _scripts = lab_env
    (cache / "manifest" / "puller-heartbeat.json").write_text(
        json.dumps({"tick_ok": 4, "tick_fail": 1, "cookie": "UID=hidden"}),
        encoding="utf-8",
    )
    counts = puller_upload_counts(cache)
    assert counts == {"ok": 4, "fail": 1, "source": "heartbeat", "window": "last_tick"}
    assert "hidden" not in json.dumps(counts)


def test_redact_still_scrubs_tokens():
    assert "secret" not in redact("refresh_token=secret UID=secret")
