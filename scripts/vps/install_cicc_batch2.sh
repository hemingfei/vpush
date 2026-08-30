#!/bin/bash
# 知识库设置增强第二批：存储机侧安装（幂等）。
# 在存储 VPS 上执行：bash install_cicc_batch2.sh
#
# 变更：
#   1. cicc_report_collector.py：40010/400013 退出前尽力写 .cicc/paused.json（quota/auth 熔断标记），
#      采集正常开跑后自动清除旧标记
#   2. cicc-status.py：status.json 增加 paused / cicc_settings 透传与 backup 节
#      （restic_last_success + restic snapshots --latest 5，env 未配 RESTIC_REPOSITORY 则诚实报未生效）
#   3. cicc-incremental.py：paused.json reason=auth 且 48h 内 → skip（quota 不跳，每日重试即恢复）；
#      cicc_settings.json 非空则按品类定向采集
#   4. cicc-dispatch.py：新增 settings（品类定向 → .cicc/cicc_settings.json）与
#      backup（后台运行 restic-backup.sh）两个命令模式
#
# 回滚：git checkout 旧版四脚本 + 采集脚本重跑本安装即可（无 unit/配置变更）。
set -euo pipefail

LIBDIR=/usr/local/lib/vpush-ima
CICC_DIR=/root/cicc
HERE=$(cd "$(dirname "$0")" && pwd)

install -m 744 "$HERE/cicc-status.py"      "$LIBDIR/cicc-status.py"
install -m 744 "$HERE/cicc-incremental.py" "$LIBDIR/cicc-incremental.py"
install -m 744 "$HERE/cicc-dispatch.py"    "$LIBDIR/cicc-dispatch.py"
install -m 744 "$HERE/../cicc_report_collector.py" "$CICC_DIR/cicc_report_collector.py"

systemctl restart vpush-cicc-dispatch.path 2>/dev/null || true
systemctl enable --now vpush-cicc-status.timer vpush-cicc-incremental.timer 2>/dev/null || true
echo "install done（备份目标 /etc/vpush/ima-storage.env 的 RESTIC_REPOSITORY 需人工配置，本脚本不改 env）"
