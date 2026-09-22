import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from arm_storage_backup import build_rsync_argv, dest_ok, main, remote_ok  # noqa: E402


def test_rsync_adds_only_and_pins_archive_root(tmp_path):
    key = tmp_path / "key"
    key.write_text("x", encoding="utf-8")
    argv = build_rsync_argv(
        source=Path("/srv/vpush-ima"),
        remote="root@198.12.125.212",
        dest_path="/srv/vpush-ima",
        key=key,
        dry_run=True,
    )
    assert "--ignore-existing" in argv
    assert "--chown=99:100" in argv
    assert "--delete" not in argv
    assert not any(part.startswith("--delete") for part in argv)
    assert "--exclude=.cicc/" in argv
    assert argv[-2] == "/srv/vpush-ima/"
    assert argv[-1] == "root@198.12.125.212:/srv/vpush-ima/"
    assert "--dry-run" in argv


def test_refuses_other_dest_and_bad_host(tmp_path):
    key = tmp_path / "key"
    key.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        build_rsync_argv(
            source=Path("/srv/vpush-ima"),
            remote="root@198.12.125.212",
            dest_path="/",
            key=key,
            dry_run=False,
        )
    with pytest.raises(ValueError):
        build_rsync_argv(
            source=Path("/srv/vpush-ima"),
            remote="root@198.12.125.212;rm",
            dest_path="/srv/vpush-ima",
            key=key,
            dry_run=False,
        )
    assert dest_ok("/srv/vpush-ima/")
    assert not dest_ok("/srv/vpush-ima/../")
    assert remote_ok("root@198.12.125.212")
    assert not remote_ok("root@host extra")


def test_default_is_off(capsys):
    assert main([]) == 0
    assert "不会 rsync" in capsys.readouterr().out
