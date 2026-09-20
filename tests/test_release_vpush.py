"""Lane A 发版入口：脚本能解析，分界文档点名四条车道。"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_release_script_is_valid_bash():
    script = ROOT / "scripts" / "release_vpush.sh"
    assert script.is_file()
    assert script.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(script)], check=True)


def test_deploy_lanes_doc_names_four_lanes():
    text = (ROOT / "docs" / "deploy-lanes.md").read_text(encoding="utf-8")
    for marker in ("Lane A", "Lane B", "Lane C", "Lane D", "release_vpush.sh"):
        assert marker in text, marker
