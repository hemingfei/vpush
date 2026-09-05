"""CICC 部署协议离线测试共享 fixture：加载 scripts/vps 生产脚本、搭控制目录。

生产脚本路径常量为模块级，测试通过 monkeypatch 模块属性注入 tmp_path；
不 SSH、不访问外网、不依赖 systemd（计划任务 1 约束）。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def load_vps_script(name: str):
    """加载 scripts/vps/<name>.py 为可测模块（纯函数直接可用；常量可 patch）。"""
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/vps/{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def cicc_archive(tmp_path):
    """离线 .cicc 控制目录（模拟存储机 /srv/vpush-ima/local/.cicc 形态）。"""
    archive = tmp_path / "archive"
    ctrl = archive / "local" / ".cicc"
    (ctrl / "commands").mkdir(parents=True)
    (ctrl / "results").mkdir(parents=True)
    return archive, ctrl