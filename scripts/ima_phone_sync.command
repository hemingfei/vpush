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
