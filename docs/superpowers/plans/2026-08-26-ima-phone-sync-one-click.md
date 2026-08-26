# IMA Phone Sync One-Click Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a macOS double-click entry that performs the existing IMA phone credential sync without requiring long command-line arguments after each phone login.

**Architecture:** Keep `scripts/ima_phone_sync.py` as the single sync implementation and add a safe allowlisted local configuration loader plus an interactive first-run setup mode. Add a thin `scripts/ima_phone_sync.command` launcher that resolves the repository root, invokes the virtualenv Python with `--one-click`, and keeps the terminal open for the result. The VPS collector and its database keys remain unchanged.

**Tech Stack:** Python 3 standard library, existing `ImaPureClient`, ADB, OpenSSH, SQLite, macOS shell launcher, pytest, Ruff.

---

### Task 1: Add failing tests for one-click configuration

**Files:**
- Modify: `tests/test_ima_phone_sync.py`
- Test: `scripts/ima_phone_sync.command` static behavior

- [ ] **Step 1: Write the failing tests**

Add tests for these public behaviors:

```python
from scripts.ima_phone_sync import (
    SyncOptions,
    load_sync_config,
    resolve_sync_options,
    save_sync_config,
)


def test_sync_config_round_trip_is_allowlisted_and_mode_600(tmp_path):
    path = tmp_path / "ima_phone_sync.env"
    options = SyncOptions(
        device="381a2bca",
        host="179.255.150.134",
        user="root",
        ssh_key="/tmp/dmit-ssh/id_rsa.pem",
        remote_db="/opt/vpush/data/dav.db",
        expected_uid="001aa361168019ef",
    )

    save_sync_config(path, options)

    assert load_sync_config(path) == options
    assert path.stat().st_mode & 0o777 == 0o600
    assert "refresh_token" not in path.read_text().lower()


def test_sync_config_rejects_unknown_fields(tmp_path):
    path = tmp_path / "ima_phone_sync.env"
    path.write_text("IMA_SYNC_HOST=example.test\nIMA_REFRESH_TOKEN=secret\n")

    with pytest.raises(ImaPhoneSyncError, match="配置项无效"):
        load_sync_config(path)


def test_resolve_sync_options_prefers_cli_values(tmp_path):
    path = tmp_path / "ima_phone_sync.env"
    save_sync_config(path, SyncOptions("phone", "old.example", "root", "old-key", "/old.db", "uid"))

    resolved = resolve_sync_options(
        config_path=path,
        cli_values={"host": "new.example", "ssh_key": "/new-key"},
    )

    assert resolved.host == "new.example"
    assert resolved.ssh_key == "/new-key"
    assert resolved.device == "phone"
    assert resolved.remote_db == "/old.db"


def test_one_click_launcher_uses_repo_root_and_virtualenv():
    launcher = (ROOT / "scripts" / "ima_phone_sync.command").read_text()

    assert "dirname" in launcher
    assert ".venv/bin/python" in launcher
    assert "--one-click" in launcher
    assert "source " not in launcher
```

Use the existing `ROOT` fixture/constants in the test module or define `ROOT = Path(__file__).resolve().parents[1]` once at module scope.

- [ ] **Step 2: Run the focused tests and verify the red phase**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_ima_phone_sync.py
```

Expected: FAIL during collection because `SyncOptions`, `load_sync_config`, `resolve_sync_options`, and `save_sync_config` do not exist, and the launcher file does not exist.

- [ ] **Step 3: Commit the red tests**

```bash
git add tests/test_ima_phone_sync.py
git commit -m "test: cover one-click IMA sync configuration"
```

### Task 2: Implement safe local configuration

**Files:**
- Modify: `scripts/ima_phone_sync.py`
- Test: `tests/test_ima_phone_sync.py`

- [ ] **Step 1: Add the configuration type and allowlist**

Add this beside `ImaCredentials`:

```python
@dataclass(frozen=True)
class SyncOptions:
    device: str = DEFAULT_ANDROID_SERIAL
    host: str = ""
    user: str = "root"
    ssh_key: str = ""
    remote_db: str = DEFAULT_REMOTE_DB
    expected_uid: str = ""


_SYNC_FIELDS = {
    "IMA_ANDROID_SERIAL": "device",
    "IMA_SYNC_HOST": "host",
    "IMA_SYNC_USER": "user",
    "IMA_SYNC_SSH_KEY": "ssh_key",
    "IMA_SYNC_REMOTE_DB": "remote_db",
    "IMA_EXPECTED_UID": "expected_uid",
}
```

- [ ] **Step 2: Implement non-shell config parsing and atomic mode-600 writes**

Add these functions:

```python
import tempfile


def load_sync_config(path: str | Path) -> SyncOptions:
    values = {
        "device": DEFAULT_ANDROID_SERIAL,
        "host": "",
        "user": "root",
        "ssh_key": "",
        "remote_db": DEFAULT_REMOTE_DB,
        "expected_uid": "",
    }
    for number, raw_line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ImaPhoneSyncError(f"同步配置第 {number} 行无效")
        key, value = (part.strip() for part in line.split("=", 1))
        field = _SYNC_FIELDS.get(key)
        if field is None:
            raise ImaPhoneSyncError(f"同步配置项无效: {key}")
        values[field] = value
    return SyncOptions(**values)


def save_sync_config(path: str | Path, options: SyncOptions) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    content = "".join(
        f"{key}={getattr(options, field)}\n" for key, field in _SYNC_FIELDS.items()
    )
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            handle.write(content)
        os.replace(temporary, target)
    except BaseException:
        if fd >= 0:
            os.close(fd)
        Path(temporary).unlink(missing_ok=True)
        raise
```

Import `tempfile` and keep the parser limited to the six non-secret fields. Do not use `source`, `eval`, or `shlex.split` for config values.

- [ ] **Step 3: Implement CLI-over-config resolution**

Add:

```python
def resolve_sync_options(
    config_path: str | Path,
    cli_values: dict[str, str] | None = None,
) -> SyncOptions:
    path = Path(config_path)
    options = load_sync_config(path) if path.exists() else SyncOptions(
        device=os.environ.get("IMA_ANDROID_SERIAL", DEFAULT_ANDROID_SERIAL),
        host=os.environ.get("IMA_SYNC_HOST", ""),
        user=os.environ.get("IMA_SYNC_USER", "root"),
        ssh_key=os.environ.get("IMA_SYNC_SSH_KEY", ""),
        remote_db=os.environ.get("IMA_SYNC_REMOTE_DB", DEFAULT_REMOTE_DB),
        expected_uid=os.environ.get("IMA_EXPECTED_UID", ""),
    )
    updates = {key: value for key, value in (cli_values or {}).items() if value not in (None, "")}
    return replace(options, **updates)
```

Import `replace` from `dataclasses`. Validate the resulting host, user, remote path, device, and expected UID through the existing command/credential validators before use. Keep all existing manual CLI arguments and their behavior unchanged.

- [ ] **Step 4: Run the focused tests**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_ima_phone_sync.py
.venv/bin/ruff check scripts/ima_phone_sync.py tests/test_ima_phone_sync.py
```

Expected: configuration tests pass; the launcher static test remains red until Task 3.

- [ ] **Step 5: Commit the configuration implementation**

```bash
git add scripts/ima_phone_sync.py tests/test_ima_phone_sync.py
git commit -m "feat: add safe IMA sync config loading"
```

### Task 3: Add first-run interactive mode and integrate the sync command

**Files:**
- Modify: `scripts/ima_phone_sync.py`
- Modify: `tests/test_ima_phone_sync.py`

- [ ] **Step 1: Add first-run prompts without token input**

Implement `_prompt_sync_options(path)` using `input()` for only the six `SyncOptions` fields. Use these defaults:

```python
DEFAULT_PROMPTS = {
    "device": DEFAULT_ANDROID_SERIAL,
    "user": "root",
    "remote_db": DEFAULT_REMOTE_DB,
}
```

Require a non-empty host and reject invalid values through the existing validators. Prompt for the expected UID and require it to pass `_validate_uid`. Save the resulting options with `save_sync_config()` and return them. Never prompt for, read, or write a Refresh Token.

- [ ] **Step 2: Add `--one-click` and `--config-file`**

Extend `_parser()` with:

```python
parser.add_argument("--one-click", action="store_true")
parser.add_argument(
    "--config-file",
    type=Path,
    default=ROOT / "data" / "ima_phone_sync.env",
)
```

In `main()`:

```python
if args.one_click:
    options = (
        _prompt_sync_options(args.config_file)
        if not args.config_file.exists()
        else load_sync_config(args.config_file)
    )
else:
    options = resolve_sync_options(
        args.config_file,
        {
            "device": args.device,
            "host": args.host,
            "user": args.user,
            "ssh_key": args.ssh_key,
            "remote_db": args.remote_db,
            "expected_uid": args.expected_uid,
        },
    )
if not options.host:
    print("缺少 VPS 地址，请首次运行完成配置", file=sys.stderr)
    return 2
```

Pass `options` into `sync_once`. Preserve the existing success output (`UID` only) and nonzero error returns.

- [ ] **Step 3: Add tests for first-run behavior**

Add tests that monkeypatch `input()` with a fixed sequence, call `_prompt_sync_options(tmp_path / "ima_phone_sync.env")`, and assert the result is saved mode `0600` with no token key. Add a test that `main(["--one-click", "--config-file", missing])` returns a configuration error when the host prompt is empty. Stub `sync_once` in the success case so the test never calls ADB, IMA, or SSH.

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_ima_phone_sync.py
```

Expected: all one-click configuration and existing sync tests pass.

- [ ] **Step 5: Commit the integrated one-click mode**

```bash
git add scripts/ima_phone_sync.py tests/test_ima_phone_sync.py
git commit -m "feat: add interactive IMA phone sync mode"
```

### Task 4: Add the double-click launcher, example config, and documentation

**Files:**
- Create: `scripts/ima_phone_sync.command`
- Create: `data/ima_phone_sync.env.example`
- Modify: `.gitignore` only if the existing `data/` rule does not ignore `data/ima_phone_sync.env`
- Modify: `README.md`
- Test: `tests/test_ima_phone_sync.py`

- [ ] **Step 1: Add the macOS launcher**

Create this executable file:

```bash
#!/bin/bash
set -u
ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  printf '找不到 %s，请先创建项目虚拟环境。\n' "$PYTHON"
  read -r -p '按回车关闭窗口...' _
  exit 1
fi

"$PYTHON" "$ROOT/scripts/ima_phone_sync.py" \
  --one-click \
  --config-file "$ROOT/data/ima_phone_sync.env"
status=$?
printf '\n同步进程已结束（状态 %s）。\n' "$status"
read -r -p '按回车关闭窗口...' _
exit "$status"
```

Run `chmod +x scripts/ima_phone_sync.command`. The launcher must not contain a host, username, SSH key path, or token and must not `source` any env file.

- [ ] **Step 2: Add the non-secret example config**

Create `data/ima_phone_sync.env.example`:

```dotenv
# Copy to data/ima_phone_sync.env; the launcher creates it on first run if absent.
IMA_ANDROID_SERIAL=381a2bca
IMA_SYNC_HOST=
IMA_SYNC_USER=root
IMA_SYNC_SSH_KEY=
IMA_SYNC_REMOTE_DB=/opt/vpush/data/dav.db
IMA_EXPECTED_UID=
```

Keep the actual `data/ima_phone_sync.env` ignored. Force-add only the example file because the repository ignores runtime data.

- [ ] **Step 3: Document the workflow**

Update the IMA section in `README.md` with:

```markdown
手机完成 IMA 登录后，双击 `scripts/ima_phone_sync.command` 即可同步；首次运行会询问 VPS 地址、SSH 私钥和 IMA UID，配置保存到 `data/ima_phone_sync.env`（0600，不含 Refresh Token）。手动排障仍可运行 `python scripts/ima_phone_sync.py`。
```

Explain that ADB must show the rooted phone and that failures remain visible in the terminal window.

- [ ] **Step 4: Add static launcher tests and run checks**

Assert the launcher contains `dirname`, `.venv/bin/python`, `--one-click`, and no `source` or `IMA_REFRESH_TOKEN`. Run:

```bash
bash -n scripts/ima_phone_sync.command
.venv/bin/ruff check scripts/ima_phone_sync.py tests/test_ima_phone_sync.py
.venv/bin/python -m pytest -q tests/test_ima_phone_sync.py
```

- [ ] **Step 5: Commit the launcher and docs**

```bash
git add .gitignore README.md scripts/ima_phone_sync.command tests/test_ima_phone_sync.py
git add -f data/ima_phone_sync.env.example
git commit -m "feat: add one-click IMA phone sync launcher"
```

### Task 5: Run regression verification and finish

**Files:**
- Verify: `scripts/ima_phone_sync.py`, `scripts/ima_phone_sync.command`, `tests/test_ima_phone_sync.py`, `README.md`, `data/ima_phone_sync.env.example`

- [ ] **Step 1: Run focused checks**

```bash
bash -n scripts/ima_phone_sync.command
.venv/bin/ruff check scripts/ima_phone_sync.py tests/test_ima_phone_sync.py
.venv/bin/python -m pytest -q tests/test_ima_phone_sync.py
```

Expected: shell syntax passes, Ruff reports no errors, and all focused tests pass.

- [ ] **Step 2: Run the full regression suite**

```bash
.venv/bin/python -m pytest -q
```

Expected: all existing tests plus the one-click tests pass; only the repository's existing deprecation warnings may remain.

- [ ] **Step 3: Verify repository hygiene and final test state**

Run:

```bash
bash -n scripts/ima_phone_sync.command
git diff --check
git status --short
```

Confirm `data/ima_phone_sync.env` is ignored, no Refresh Token appears in tracked files, and unrelated existing research files remain unstaged.
