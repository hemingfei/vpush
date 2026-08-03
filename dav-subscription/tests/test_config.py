from app.config import load_config


def test_defaults_without_file(tmp_path, monkeypatch):
    monkeypatch.delenv("CONFIG_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    config = load_config(tmp_path / "nope.yaml")
    assert config.polling.interval_seconds == 180
    assert config.notifiers.feishu.webhook_url == ""
    assert config.db_path == "/data/dav.db"


def test_yaml_and_env_overrides(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text(
        "polling:\n  interval_seconds: 60\nweb:\n  password: secret\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("POLLING_INTERVAL_SECONDS", "90")
    config = load_config(tmp_path / "config.yaml")
    assert config.polling.interval_seconds == 90
    assert config.web.password == "secret"
