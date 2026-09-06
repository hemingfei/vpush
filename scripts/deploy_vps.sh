#!/usr/bin/env bash
# 云端一键部署：数据库备份 → docker load 镜像包 → tag 对齐 → compose 重建 → 健康检查 → 清理
# 放到服务器部署目录（与 docker-compose.prod.yml 同级），用法：
#   ./deploy_vps.sh                     部署 vpush-latest.tar（默认文件名）
#   ./deploy_vps.sh vpush-xxx.tar.gz    部署指定镜像包（gzip 压缩包也可，docker load 自动解压）
#   ./deploy_vps.sh --rollback          回滚到上一次部署前的镜像
# 可选环境变量：
#   SKIP_BACKUP=1   跳过部署前数据库备份
#   BACKUP_KEEP=14  部署前备份保留份数（默认 14）
set -euo pipefail
cd "$(dirname "$0")"

TAR="${1:-vpush-latest.tar}"
BACKUP_KEEP="${BACKUP_KEEP:-14}"
COMPOSE=(docker compose -f docker-compose.prod.yml -f docker-compose.override.yml)

log() { echo "==> $*"; }
die() { echo "!! $*" >&2; exit 1; }

# compose 合并 override 后实际引用的镜像列表（每行一个，如 vpush:latest）
expected_images() { "${COMPOSE[@]}" config --images; }

# 从运行中的容器取实际宿主机端口（服务器上 8888 可能被占而改用 8889 等，不写死）
host_port() {
  local p
  p=$(docker port vpush 8000 2>/dev/null | head -n1 | awk -F: '{print $NF}') || true
  if [ -z "$p" ]; then
    p=$("${COMPOSE[@]}" config 2>/dev/null | sed -n 's/.*published: "\([0-9]*\)".*/\1/p' | head -n1) || true
  fi
  echo "${p:-8888}"
}

health_check() {
  local port ok=""
  port=$(host_port)
  log "健康检查 http://127.0.0.1:${port}/healthz"
  for _ in $(seq 1 30); do
    if curl -fsS -m 5 "http://127.0.0.1:${port}/healthz" >/dev/null 2>&1; then ok=1; break; fi
    sleep 2
  done
  if [ -z "$ok" ]; then
    echo "!! 健康检查未通过（等待约 1 分钟），vpush 最近 50 行日志：" >&2
    docker logs --tail 50 vpush || true
    exit 1
  fi
  printf '==> 部署后版本: '
  curl -fsS -m 5 "http://127.0.0.1:${port}/api/version" 2>/dev/null || echo "(未取到 /api/version)"
  echo
}

# 容器必须运行在 compose 所指镜像的当前 ID 上；若不一致说明 up -d 跳过了重建（旧容器还在跑）
assert_running_on_current_image() {
  local c running cfg current
  for c in vpush vpush-waf-bot; do
    docker ps --format '{{.Names}}' | grep -qx "$c" || die "容器未运行: $c（看上面 compose 输出排查）"
    running=$(docker inspect -f '{{.Image}}' "$c")
    cfg=$(docker inspect -f '{{.Config.Image}}' "$c")
    current=$(docker image inspect -f '{{.Id}}' "$cfg")
    if [ "$running" != "$current" ]; then
      die "$c 未运行在最新镜像上（容器 $(printf '%s' "$running" | cut -c8-19)，镜像 $cfg 当前指向 $(printf '%s' "$current" | cut -c8-19)）。执行 ${COMPOSE[*]} up -d --force-recreate 可强制重建"
    fi
  done
}

# ---- 回滚模式：把部署前留在 <repo>:rollback 的上一版镜像指回 compose 引用的 tag ----
if [ "${1:-}" = "--rollback" ]; then
  ROLLED=0
  while IFS= read -r img; do
    [ -n "$img" ] || continue
    if docker image inspect "${img%:*}:rollback" >/dev/null 2>&1; then
      log "把 $img 指回上一版（${img%:*}:rollback）"
      docker tag "${img%:*}:rollback" "$img"
      ROLLED=1
    else
      echo "!! 无回滚镜像 ${img%:*}:rollback（该服务没有部署过旧版本），跳过"
    fi
  done <<< "$(expected_images)"
  [ "$ROLLED" = "1" ] || die "没有任何服务完成回滚"
  log "重建容器"
  "${COMPOSE[@]}" up -d
  assert_running_on_current_image
  health_check
  log "已回滚 ✔"
  exit 0
fi

# ---- 前置检查 ----
command -v curl >/dev/null || die "需要 curl"
[ -f "$TAR" ] || die "镜像包不存在: $TAR（用法: $0 [镜像包路径]）"
[ -f docker-compose.prod.yml ] && [ -f docker-compose.override.yml ] || \
  die "缺少 compose 文件：脚本必须与 docker-compose.prod.yml / docker-compose.override.yml 放在同一目录"
docker compose version >/dev/null 2>&1 || die "docker compose v2 不可用"
EXPECTED_IMAGES=$(expected_images)
[ -n "$EXPECTED_IMAGES" ] || die "解析 compose 镜像列表失败"

# ---- 部署前数据库在线备份（WAL 安全，落在 data/backups/，保留最近 BACKUP_KEEP 份）----
if [ "${SKIP_BACKUP:-0}" != "1" ] && docker ps --format '{{.Names}}' | grep -qx vpush; then
  log "部署前备份数据库 -> data/backups/"
  docker exec -i -e BACKUP_KEEP="$BACKUP_KEEP" vpush python - <<'PY'
import os, pathlib, sqlite3, time
keep = int(os.environ.get("BACKUP_KEEP", "14"))
b = pathlib.Path("/data/backups"); b.mkdir(exist_ok=True)
t = b / ("dav-%s.db" % time.strftime("%Y%m%d-%H%M%S"))
src = sqlite3.connect("/data/dav.db"); dst = sqlite3.connect(t)
try:
    with dst:
        src.backup(dst)
finally:
    dst.close(); src.close()
ok = sqlite3.connect(t).execute("PRAGMA quick_check").fetchone()[0]
if ok != "ok":
    t.unlink()
    raise SystemExit("备份校验失败: %s" % ok)
for old in sorted(b.glob("dav-*.db"))[:-keep]:
    old.unlink()
print("备份完成:", t.name)
PY
elif [ "${SKIP_BACKUP:-0}" != "1" ]; then
  log "vpush 容器未在运行，跳过备份（可能是首次部署）"
fi

# ---- 给当前版本留回滚 tag（<repo>:rollback，每次部署覆盖，磁盘上永远保留上一版）----
while IFS= read -r img; do
  [ -n "$img" ] || continue
  if docker image inspect "$img" >/dev/null 2>&1; then
    docker tag "$img" "${img%:*}:rollback"
  fi
done <<< "$EXPECTED_IMAGES"

# ---- 加载镜像包 ----
log "加载镜像包: $TAR"
# 2>&1：部分 docker 版本把 "Loaded image:" 行打到 stderr，一并捕获再解析
LOAD_OUTPUT=$(docker load -i "$TAR" 2>&1)
LOADED_TAGS=$(printf '%s\n' "$LOAD_OUTPUT" | sed -n 's/^Loaded image: //p')
if [ -n "$LOADED_TAGS" ]; then
  printf '已加载镜像:\n%s\n' "$LOADED_TAGS"
else
  echo "$LOAD_OUTPUT"
  echo "!! 未能从 docker load 输出解析镜像 tag，继续部署（由镜像校验与重建确认兜底）"
fi

# ---- tag 对齐：override 若引用版本号 tag 而 tar 里是 latest，把 latest 重打到该 tag ----
# 否则 up -d 会命中旧的版本 tag：镜像"存在"导致容器不重建，部署等于没发生
while IFS= read -r img; do
  [ -n "$img" ] || continue
  case "$img" in *:latest) continue ;; esac
  if printf '%s\n' "$LOADED_TAGS" | grep -Fxq "${img%:*}:latest"; then
    log "重打标签: ${img%:*}:latest -> $img"
    docker tag "${img%:*}:latest" "$img"
  fi
done <<< "$EXPECTED_IMAGES"

# ---- 校验 compose 引用的镜像本地已存在（防止误拉 Docker Hub 上的同名旧镜像 / image not found）----
while IFS= read -r img; do
  [ -n "$img" ] || continue
  docker image inspect "$img" >/dev/null 2>&1 || \
    die "compose 引用的镜像不存在: $img（tar 加载到: ${LOADED_TAGS:-无}）。请把 override 里的 image 改成 tar 实际 tag 后重试"
done <<< "$EXPECTED_IMAGES"

# ---- 重建 ----
log "重建容器"
"${COMPOSE[@]}" up -d --remove-orphans

assert_running_on_current_image
health_check

# ---- 清理悬空镜像（<repo>:rollback 有 tag 不受影响，旧版本保留可回滚）----
docker image prune -f >/dev/null
log "已清理悬空镜像"
log "部署完成 ✔"
