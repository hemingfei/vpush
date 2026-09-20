#!/usr/bin/env bash
# Lane A：vpush.net 现网发版。只动 DMIT 上的 vpush，不碰 Unraid / ARM / 存储 / waf-bot。
# 用法：
#   ./scripts/release_vpush.sh          # 版本已对齐，工作区干净或只剩发版文件
#   ./scripts/release_vpush.sh --bump   # 补丁 +0.0.1 后发
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

PROD_HOST="${VPUSH_HOST:-root@179.255.150.134}"
PROD_SRC="/opt/vpush/src"
PROD_COMPOSE="/opt/vpush"
LOCAL_IMAGE="dav-subscription-vpush:latest"
SSH_KEY="${VPUSH_SSH_KEY:-/tmp/dmit-ssh/id_rsa.pem}"
SSH_ZIP="${VPUSH_SSH_ZIP:-/Volumes/main/DMIT-thaXVWahhp-id_rsa.zip}"
SSH_OPTS=(-i "$SSH_KEY" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=15)

BUMP=0
DRY_RUN=0
NOTES=""

usage() {
  cat <<'EOF'
Lane A 现网发版（vpush.net / DMIT overlay）。

  ./scripts/release_vpush.sh [--bump] [--notes TEXT] [--dry-run]

  --bump     APP_VERSION 补丁 +1，并 sync 静态 hash
  --notes    GitHub Release 说明（默认用上一标签以来的 commit 标题）
  --dry-run  预检到打印动作为止，不 commit / 不推送 / 不上 VPS

不改远端 .env / data / compose，不重建 waf-bot，不 SSH Unraid / ARM / 存储。
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bump) BUMP=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --notes)
      NOTES="${2:-}"
      [[ -n "$NOTES" ]] || { echo "缺少 --notes 文本" >&2; exit 2; }
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -x .venv/bin/python ]]; then
  PY=.venv/bin/python
else
  PY=python3
fi

log() { printf '== %s ==\n' "$*"; }

read_py_version() {
  "$PY" - <<'PY'
from pathlib import Path
import re
text = Path("app/version.py").read_text(encoding="utf-8")
match = re.search(r'APP_VERSION = "([^"]+)"', text)
if not match:
    raise SystemExit("app/version.py 没有 APP_VERSION")
print(match.group(1))
PY
}

read_js_version() {
  "$PY" - <<'PY'
from pathlib import Path
import re
text = Path("app/static/app.js").read_text(encoding="utf-8")
match = re.search(r'const APP_VERSION = "([^"]+)"', text)
if not match:
    raise SystemExit("app/static/app.js 没有 APP_VERSION")
print(match.group(1))
PY
}

next_patch_version() {
  "$PY" - <<'PY'
from pathlib import Path
import re
text = Path("app/version.py").read_text(encoding="utf-8")
match = re.search(r'APP_VERSION = "(\d+)\.(\d+)\.(\d+)"', text)
if not match:
    raise SystemExit("app/version.py 没有 APP_VERSION")
major, minor, patch = (int(part) for part in match.groups())
print(f"{major}.{minor}.{patch + 1}")
PY
}

hashed_assets() {
  "$PY" - <<'PY'
from pathlib import Path
import re
html = Path("app/static/index.html").read_text(encoding="utf-8")
app = re.search(r"/app\.[0-9a-f]{12}\.js", html)
style = re.search(r"/style\.[0-9a-f]{12}\.css", html)
if not app:
    raise SystemExit("index.html 没有 /app.<hash>.js")
print(app.group(0))
print(style.group(0) if style else "")
PY
}

bump_patch() {
  "$PY" - <<'PY'
from pathlib import Path
import re

def bump(path: Path, pattern: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(pattern, text)
    if not match:
        raise SystemExit(f"{path} 没有版本号")
    major, minor, patch = (int(part) for part in match.groups())
    nxt = f"{major}.{minor}.{patch + 1}"
    path.write_text(text[: match.start(1)] + nxt + text[match.end(3) :], encoding="utf-8")
    return nxt

py_ver = bump(Path("app/version.py"), r'APP_VERSION = "(\d+)\.(\d+)\.(\d+)"')
js_ver = bump(Path("app/static/app.js"), r'const APP_VERSION = "(\d+)\.(\d+)\.(\d+)"')
if py_ver != js_ver:
    raise SystemExit(f"bump 后版本不一致: {py_ver} vs {js_ver}")
print(py_ver)
PY
}

ensure_ssh_key() {
  if [[ -f "$SSH_KEY" ]]; then
    return
  fi
  [[ -f "$SSH_ZIP" ]] || { echo "没有 SSH 密钥: $SSH_KEY 且找不到 $SSH_ZIP" >&2; exit 1; }
  mkdir -p /tmp/dmit-ssh
  chmod 700 /tmp/dmit-ssh
  unzip -o "$SSH_ZIP" -d /tmp/dmit-ssh
  chmod 600 /tmp/dmit-ssh/*
  [[ -f "$SSH_KEY" ]] || { echo "解压后仍没有 $SSH_KEY" >&2; exit 1; }
}

ssh_prod() {
  ssh "${SSH_OPTS[@]}" "$PROD_HOST" "$@"
}

release_files_ok() {
  local path
  while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    case "$path" in
      app/version.py|app/static/app.js|app/static/index.html|app/static/sw.js) ;;
      *) return 1 ;;
    esac
  done
  return 0
}

branch="$(git rev-parse --abbrev-ref HEAD)"
[[ "$branch" == "main" ]] || { echo "必须在 main 上发版，当前是 $branch" >&2; exit 1; }

log "预检"
git fetch origin
if [[ "$(git rev-list --count HEAD.."origin/main" 2>/dev/null || echo 1)" != 0 ]]; then
  echo "origin/main 有未合并提交，先拉再发" >&2
  exit 1
fi
git diff --check

if [[ "$BUMP" -eq 1 && "$DRY_RUN" -eq 1 ]]; then
  VERSION="$(next_patch_version)"
  JS_VERSION="$(read_js_version)"
  CUR="$(read_py_version)"
  [[ "$CUR" == "$JS_VERSION" ]] || {
    echo "版本不一致: version.py=$CUR app.js=$JS_VERSION" >&2
    exit 1
  }
  log "dry-run 将 bump ${CUR} → ${VERSION}"
elif [[ "$BUMP" -eq 1 ]]; then
  VERSION="$(bump_patch)"
  log "版本 bump → $VERSION"
  "$PY" scripts/bump_assets.py --sync
  JS_VERSION="$(read_js_version)"
  [[ "$VERSION" == "$JS_VERSION" ]] || {
    echo "版本不一致: version.py=$VERSION app.js=$JS_VERSION" >&2
    exit 1
  }
else
  VERSION="$(read_py_version)"
  JS_VERSION="$(read_js_version)"
  [[ "$VERSION" == "$JS_VERSION" ]] || {
    echo "版本不一致: version.py=$VERSION app.js=$JS_VERSION" >&2
    exit 1
  }
fi
"$PY" scripts/bump_assets.py --check

ASSET_LINES="$(hashed_assets)"
APP_JS="$(printf '%s\n' "$ASSET_LINES" | sed -n '1p')"
APP_STYLE="$(printf '%s\n' "$ASSET_LINES" | sed -n '2p')"
TAG="v${VERSION}"
PREV_TAG="$(git tag -l 'v*' --sort=v:refname | grep -v "^${TAG}$" | tail -1 || true)"
[[ -n "$PREV_TAG" ]] || { echo "找不到上一标签，无法选 overlay FROM" >&2; exit 1; }

if git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null; then
  echo "本地已有标签 ${TAG}" >&2
  exit 1
fi
if git ls-remote --tags origin "refs/tags/${TAG}" | grep -q .; then
  echo "远端已有标签 ${TAG}" >&2
  exit 1
fi

dirty="$(git status --porcelain)"
if [[ -n "$dirty" ]]; then
  if ! git status --porcelain | awk '{print $NF}' | release_files_ok; then
    echo "工作区有非发版文件，先提交或清掉：" >&2
    git status --short >&2
    exit 1
  fi
fi

log "测试"
if [[ -d app/static ]]; then
  find app/static -type f -name '*.js' -print0 | while IFS= read -r -d '' file; do
    node --input-type=module --check < "$file"
  done
fi
"$PY" -m pytest -q

if [[ -z "$NOTES" ]]; then
  NOTES="$(git log --pretty=format:'- %s' "${PREV_TAG}..HEAD")"
  if [[ -n "$dirty" || "$BUMP" -eq 1 ]]; then
    NOTES="${NOTES:+$NOTES$'\n'}- 发布 ${TAG}"
  fi
  [[ -n "$NOTES" ]] || NOTES="release ${TAG}"
fi

log "将发布 ${TAG}（FROM icekale/vpush:${PREV_TAG}，静态 ${APP_JS}）"
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "dry-run：跳过 commit / 推送 / overlay"
  exit 0
fi

if [[ -n "$(git status --porcelain)" ]]; then
  git add -- app/version.py app/static/app.js app/static/index.html app/static/sw.js
  git commit -m "chore: 发布 ${TAG}"
fi

git push origin HEAD
git tag -a "$TAG" -m "release ${TAG}"
git push origin "$TAG"
gh release create "$TAG" --title "$TAG" --notes "$NOTES"
echo "CI："
gh run list --workflow docker-publish.yml --limit 2 || true

log "VPS overlay"
ensure_ssh_key
ssh_prod "mkdir -p '${PROD_SRC}/app'"
rsync -az --delete --exclude '__pycache__/' --exclude '*.pyc' \
  -e "ssh ${SSH_OPTS[*]}" \
  app/ "${PROD_HOST}:${PROD_SRC}/app/"

# 远端确认后再 overlay。不改 .env / data / compose，不 build waf-bot。
ssh_prod "test -d '${PROD_SRC}/app' && grep -n 'APP_VERSION' '${PROD_SRC}/app/version.py' '${PROD_SRC}/app/static/app.js' && grep -F '${APP_JS}' '${PROD_SRC}/app/static/index.html'"
ssh_prod "cat > '${PROD_SRC}/Dockerfile.overlay' <<EOF
FROM icekale/vpush:${PREV_TAG}
COPY --chown=99:100 app ./app
EOF
cd '${PROD_SRC}' && DOCKER_BUILDKIT=0 docker build -f Dockerfile.overlay -t '${LOCAL_IMAGE}' .
cd '${PROD_COMPOSE}' && docker compose up -d --no-deps vpush"

log "健康检查"
ok=0
for _ in $(seq 1 24); do
  status="$(ssh_prod "docker inspect --format '{{.State.Status}} {{.State.Health.Status}}' vpush")"
  if [[ "$status" == "running healthy" ]]; then
    ok=1
    break
  fi
  sleep 2
done
[[ "$ok" -eq 1 ]] || { echo "容器未 healthy: ${status:-unknown}" >&2; exit 1; }

remote_health="$(ssh_prod "docker exec vpush python -c 'import urllib.request; print(urllib.request.urlopen(\"http://127.0.0.1:8000/healthz\", timeout=8).read().decode())'")"
echo "$remote_health" | grep -q '"status":"ok"' || { echo "容器 /healthz 异常: $remote_health" >&2; exit 1; }
ssh_prod "docker exec vpush grep -n APP_VERSION /app/app/version.py /app/app/static/app.js" | grep -F "$VERSION" >/dev/null

live_health="$(curl -fsS https://vpush.net/healthz)"
echo "$live_health" | grep -q '"status":"ok"' || { echo "线上 /healthz 异常: $live_health" >&2; exit 1; }
live_html="$(curl -fsS https://vpush.net/)"
echo "$live_html" | grep -F "$APP_JS" >/dev/null || { echo "线上缺少 ${APP_JS}" >&2; exit 1; }
if [[ -n "$APP_STYLE" ]]; then
  echo "$live_html" | grep -F "$APP_STYLE" >/dev/null || { echo "线上缺少 ${APP_STYLE}" >&2; exit 1; }
fi

echo
echo "Lane A 完成：${TAG}"
echo "健康：${live_health}"
echo "静态：${APP_JS}${APP_STYLE:+ ${APP_STYLE}}"
echo "镜像还在 CI（不要 gh run watch）"
echo "/healthz/ima-storage 不作为完成门闩"
