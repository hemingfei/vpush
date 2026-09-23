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


@pytest.fixture(autouse=True)
def _stub_xueqiu_app_identity(monkeypatch):
    """雪球只有 App 隐式账号一条身份通道（网页 cookie 兜底已于 2026-09-23 下线）。

    这里 stub 掉注册与轮换：既不向雪球发真实请求，又让所有用例走生产真实路径。
    需要验证注册/续期失败分支的用例，自行覆盖 `xq_identity.identity`。
    """
    monkeypatch.setenv("XUEQIU_APP_IDENTITY", "1")
    fake_identity = {
        "cookie": "xq_a_token=app-token; u=2431759417",
        "uid": 2431759417,
        "device_id": "1ONEPLUS" + "0" * 32,
    }
    monkeypatch.setattr("app.xq_identity.identity", lambda: dict(fake_identity))
    monkeypatch.setattr("app.xq_identity.rotate_identity", lambda: dict(fake_identity))