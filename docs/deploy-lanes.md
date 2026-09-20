# 部署车道

一个 git 仓库里住了四套独立部署单元。说「发版」默认只指 **Lane A**。不要整仓一起发。

现网只认 [vpush.net](https://vpush.net/)（DMIT）。家里 Unraid 是测试机，不是第五条产品车道。

## 先问哪条车道

| 车道 | 改什么 | 上哪 | 命令 | 不要做 |
| --- | --- | --- | --- | --- |
| **A · V Push 现网** | `app/`、`requirements.txt`、`Dockerfile` | DMIT `/opt/vpush` | `scripts/release_vpush.sh` | 重建 waf-bot；SSH Unraid / ARM / 存储；等 Hub 镜像 |
| **B · waf-bot** | `waf-bot/` | 现网或 Unraid 宿主机 sidecar | 该主机 `docker compose build waf-bot && up -d waf-bot` | 跟着 Lane A 顺手重建 |
| **C · 实验室与冷备** | `arm-lab-ops/`、`deploy/ima-storage/`、`scripts/puller_loop.py`、`scripts/cicc_*.py`、`scripts/ima_arm_*.py` | Oracle ARM / 存储 VPS systemd | 各机 systemd；见 [ARM中间层架构.md](ARM中间层架构.md) | 挂进现网 NFS；开 `VPUSH_ARM_MIDDLEWARE`；当现网发版 |
| **D · 客户端** | `miniprogram/`、`mobile/flutter_app/`、`android-twa/` | 各自商店 / 侧载 | 各自 CI（Flutter 已 path-filter） | 跟网页发版绑在一起 |

Unraid：`scripts/deploy_unraid.sh` 只测代码，不进发布。

## Lane A

- 流程：预检 → 推 `main` → 打 `vX.Y.Z` → 建 Release → rsync `app/` → `Dockerfile.overlay` → `docker compose up -d --no-deps vpush`。
- 脚本：`scripts/release_vpush.sh`（补丁号 +1 加 `--bump`）。Agent 先跑脚本，失败再按 `.cursor/skills/vpush-release-deploy/SKILL.md` 手工。
- 完成：`main` + 标签已推；GitHub Release 已建；容器 `running healthy`；`https://vpush.net/healthz` 为 `{"status":"ok"}`；线上静态 hash 与本次 `index.html` 一致。
- `/healthz/ima-storage` 503 **不挡**完成。Hub / GHCR 是后台产物，不要 `gh run watch`。
- 不要改远端 `.env`、`data/`、compose。不要 `compose build waf-bot`。

IMA / 中金的**产品代码**在 `app/` 里，跟网页一起 overlay。IMA / 中金的**机房**是 Lane C，跟这次发版无关。

## Lane B

只在 `waf-bot/` 有改动时重建 sidecar。官方 `icekale/vpush` 镜像不含 waf-bot。

## Lane C

生产禁止挂 ARM / 存储 NFS，禁止在现网 compose 开中间层。vpush 缺文件只走 HTTP `IMA_PULL_URL`（超时 + 熔断）。口径：[ARM中间层架构.md](ARM中间层架构.md)、[deploy/ima-storage/README.md](../deploy/ima-storage/README.md)。

## Lane D

网页是主界面。小程序暂停；Flutter / TWA 单独发 APK。

## 自托管

别人用官方镜像或本仓库 Compose 起自己的实例，看根目录 [README.md](../README.md)「快速 Docker 部署」。那不是 vpush.net 发版。
