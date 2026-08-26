# IMA 手机凭据一键同步设计

## 目标

手机在 rooted Android 的 IMA 应用中重新完成 Google 登录后，用户只需双击一个 macOS `.command` 文件即可把新的 IMA Refresh Token 同步到 VPS。现有 IMA 文档采集器、SQLite setting key 和 VPS 运行方式保持不变。

## 非目标

- 不实现常驻 watcher、LaunchAgent 或后台轮询。
- 不改变 VPS 的采集接口或前端管理后台。
- 不保存 Google access token、Google id token 或一次性授权 code。
- 不把 Refresh Token 放进 Git、shell 参数、日志或双击脚本内容。

## 用户流程

### 首次配置

`ima_phone_sync.command` 检测到本地配置文件不存在时，在终端中提示填写：

- Android ADB serial，默认 `381a2bca`
- VPS host
- SSH user，默认 `root`
- SSH private key path
- 远端数据库路径，默认 `/opt/vpush/data/dav.db`
- 期望的 IMA UID

工具只把这些连接和账户约束写入 `data/ima_phone_sync.env`，创建后设置为 `0600`。配置文件不包含 Refresh Token。

### 日常同步

1. 用户在手机 IMA 中完成 Google 登录。
2. 手机通过 ADB 保持连接并授权 root shell。
3. 用户双击 `scripts/ima_phone_sync.command`。
4. 启动器进入仓库根目录，调用项目虚拟环境中的 Python 脚本。
5. Python 脚本读取配置，ADB 获取 `pref_login_response`，校验 UID/Refresh Token。
6. 通过 IMA refresh 接口验证 Refresh Token。
7. 将 UID 和 Refresh Token 作为 JSON stdin 传给 SSH；远端脚本在一个 SQLite 事务中更新两个 settings。
8. 终端只显示 UID、成功/失败状态，等待用户按回车关闭窗口。

现有手动 CLI 参数继续可用，便于无 Finder 环境或自动化测试调用。

## 组件

### `scripts/ima_phone_sync.py`

在现有同步逻辑上增加：

- 允许列表式 `.env` 配置读取，不执行配置文件中的 shell 内容。
- `--one-click`/交互配置模式：首次缺配置时提示并原子写入 `data/ima_phone_sync.env`。
- 配置文件权限检查和敏感字段拒绝，配置只允许设备、主机、SSH 用户/密钥、远端 DB、期望 UID 等非 token 字段。
- 保留现有 ADB XML 解析、IMA refresh 验证、SSH stdin 传输和 UID 不匹配保护。
- 错误摘要继续清理 URL、token 形态和上游 traceback，不打印 XML 或 token。

### `scripts/ima_phone_sync.command`

macOS Finder 可双击的极薄启动器：

- 计算仓库根目录，不依赖当前工作目录。
- 优先使用 `.venv/bin/python`，缺失时给出明确错误。
- 调用 `ima_phone_sync.py --one-click`。
- 保留终端窗口，显示最终状态，避免用户看不到失败原因。
- 不在脚本中写入 host、用户名、私钥路径或任何凭据。

### 本地配置

- 新增 `data/ima_phone_sync.env.example`，只包含非敏感连接配置示例。
- `.gitignore` 忽略 `data/ima_phone_sync.env`。
- 写入使用临时文件 + `os.replace`，并设置 `0600`。
- 不使用 `source` 或 `eval` 加载配置。

## 数据流与安全

```text
IMA Android shared_prefs
        |
        | ADB stdout（本地内存）
        v
pref_login_response -> UID/Refresh Token 校验
        |
        | HTTPS IMA refresh（只验证，不保存短 token）
        v
SSH stdin JSON（命令参数不含 token）
        |
        v
VPS Python + SQLite transaction
        |
        +-- ima_pure_uid
        +-- ima_pure_refresh_token
```

远端更新前检查现有 `ima_pure_uid`。已有 UID 与手机 UID 不一致时拒绝写入；事务回滚，避免把一个账户的 token 写到另一个账户下。Refresh Token 只存在于 Python 进程内存、HTTPS 请求体、SSH stdin 和远端 settings 数据库中。

## 错误处理

- ADB 无设备、root shell 失败或 XML 缺失：提示重新连接/登录手机。
- JSON、UID 或 Refresh Token 无效：拒绝同步，不连接 VPS。
- IMA refresh 失败：拒绝写入 VPS。
- SSH 或远端 SQLite 失败：显示脱敏错误，不输出 stdin 内容。
- 任一失败都返回非零退出码；双击入口会保留窗口。

## 测试

在现有 `tests/test_ima_phone_sync.py` 基础上增加：

- 配置文件解析、未知字段拒绝、权限与原子写入。
- 首次交互配置使用默认值和缺少必填 host 的错误。
- `.command` 使用仓库根目录和虚拟环境 Python。
- 现有 XML 提取、UID 校验、IMA refresh mock、SSH stdin 不泄露、远端 SQLite 原子更新和 UID 回滚测试继续通过。

验证命令：

```bash
.venv/bin/python -m pytest -q tests/test_ima_phone_sync.py
.venv/bin/ruff check scripts/ima_phone_sync.py tests/test_ima_phone_sync.py
```

## 取舍

选择双击入口而不是常驻 watcher：每次登录后仍需要一次明确的用户动作，但不会增加后台常驻进程、LaunchAgent 生命周期、断线重试和日志管理。该方案覆盖“不要再输入长命令”的主要摩擦，改动最小，也保留手动 CLI 作为故障排查入口。
