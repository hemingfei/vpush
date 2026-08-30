# Docker 离线部署与升级指南

适用场景：本地（Windows）构建镜像，导出 tar 上传到云端服务器（Ubuntu 22.04 / x86_64）直接启动，服务器无需项目源码、无需联网拉取依赖。

## 一、文件清单（服务器上需要的）

假设服务器部署目录为 `/root/VPush/`：

| 文件 | 来源 | 作用 |
|---|---|---|
| `vpush-<版本>.tar` | 本地 `docker save` 导出 | 包含两个镜像（主应用 + waf-bot） |
| `docker-compose.prod.yml` | 项目根目录 | 容器编排（端口、挂载、环境变量） |
| `docker-compose.override.yml` | 见下文模板 | 把 compose 里的 `build:` 替换成已加载的镜像 |
| `config.yaml` | 本地项目根目录 | 应用配置（挂载为容器内 `/data/config.yaml`） |
| `.env` | 本地项目根目录 | 敏感变量（飞书/Telegram/cookie 等），不进镜像 |
| `data/` | 可选：迁移旧数据时才传 | 数据库、日志、cookie 等持久化数据 |

`docker-compose.override.yml` 内容模板（`<版本>` 换成实际版本号，如 1.12.96）：

```yaml
services:
  vpush:
    image: vpush:<版本>
    build: !reset null
  waf-bot:
    image: vpush-waf-bot:<版本>
    build: !reset null
```

## 二、首次部署

### 1. 本地：构建并导出镜像（在项目根目录）

```bash
docker build -t vpush:<版本> .
docker build -t vpush-waf-bot:<版本> ./waf-bot

# 两个镜像一起打进一个 tar
docker save vpush:<版本> vpush-waf-bot:<版本> -o vpush-<版本>.tar

# 可选：压缩后传输（服务器上先 gunzip）
# gzip vpush-<版本>.tar
```

本地是 Windows x64、服务器是 x86_64，架构一致，无需 `--platform`。
国内网络慢可给主镜像加：`--build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`。

### 2. 上传文件到服务器

```bash
scp vpush-<版本>.tar docker-compose.prod.yml config.yaml .env root@服务器IP:/root/VPush/
```

注意 `config.yaml` 和 `.env` 含敏感信息，只走 SSH/可信渠道。

### 3. 服务器：加载镜像并启动

```bash
cd /root/VPush
docker load -i vpush-<版本>.tar

# 创建 override（首次部署做一次，以后只改里面的版本号）
cat > docker-compose.override.yml <<'EOF'
services:
  vpush:
    image: vpush:<版本>
    build: !reset null
  waf-bot:
    image: vpush-waf-bot:<版本>
    build: !reset null
EOF

# 启动（两个 -f 必须都带，否则 compose 会尝试 build）
docker compose -f docker-compose.prod.yml -f docker-compose.override.yml up -d
```

### 4. 验证

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.override.yml ps
curl http://localhost:8889/healthz     # 正常返回即成功
docker logs -f vpush                   # 看启动日志
```

浏览器访问 `http://服务器公网IP:8889`。云安全组和防火墙（宝塔）需放行对应端口。
服务器 8888 被宝塔 phpMyAdmin 占用，本项目使用 **8889**（在 `docker-compose.prod.yml` 的 `ports` 段，改冒号前的宿主机端口，冒号后的 8000 不要动）。

## 三、版本升级

1. 本地重复「构建 + 导出」（用新版本号，如 `vpush:1.12.97`）；
2. `scp` 上传新 tar，服务器 `docker load`；
3. 修改 `docker-compose.override.yml` 里两个 image 的 tag 为新版本；
4. 重新启动（compose 自动重建容器）：

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.override.yml up -d
```

数据都在 `data/` 和 `config.yaml` 里，升级不受影响。回滚就是把 override 里的 tag 改回旧版本再 `up -d`。旧镜像确认不用后可 `docker image prune -a` 清理。

## 四、权限与已知坑（重要）

容器以 `user: "99:100"` 运行且根文件系统只读（安全加固），所有写入都落在 bind mount 里，因此宿主机上对应的文件/目录必须允许 uid 99 写入：

```bash
chown -R 99:100 /root/VPush/data
chown 99:100 /root/VPush/config.yaml
```

部署或迁移后如果出现以下报错，都是同一个修法（对报错路径对应的宿主机文件 `chown 99:100`）：

- `PermissionError: [Errno 13] Permission denied: '/data/...'`
- 网页保存配置失败 `Read-only file system: 'config.yaml'`（config.yaml 不可写导致降级也失败）

其他注意事项：

- **`-f` 与 override**：显式指定 `-f docker-compose.prod.yml` 时，`docker-compose.override.yml` 不会被自动加载，必须同时 `-f` 传入两个文件；
- **`.env` 的 `LOG_FILE` 必须是绝对路径** `/data/logs/app.log`（相对路径会在只读文件系统上创建失败导致容器循环崩溃）；`DB_PATH` 已由 compose 写死为 `/data/dav.db`，不受 `.env` 影响；
- **bind mount 源必须存在**：`config.yaml` 如果上传时漏了，Docker 会自动创建同名空目录顶替，导致应用读不到配置——挂载前先确认文件存在；
- **端口冲突**：服务器 8888 被宝塔占用，本项目用 8889；
- **配置以服务器为准**：网页后台改配置会写回服务器的 `/root/VPush/config.yaml`，之后不要用本地旧配置覆盖它；
- **备份**：备份 `/root/VPush/` 下的 `data/`、`config.yaml`、`.env`、两个 compose 文件即可，镜像可随时重新构建。
