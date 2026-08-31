#!/bin/bash
# 知识库设置增强第三批：存储机侧安装（幂等）。
# 在存储 VPS 上执行：bash install_cicc_batch3.sh
#
# 变更：
#   1. 安装 cicc-consistency.py（本地库一致性体检，写 .cicc/consistency.json）
#   2. 更新 cicc-status.py（status.json 透传 consistency 报告）/ cicc-dispatch.py
#      （新增 consistency/dedup 模式）/ cicc-incremental.py（关键词白名单透传）
#   3. 更新 /root/cicc/cicc_report_collector.py（--keywords 标题白名单）
#   4. 新增 vpush-cicc-dedup.timer（每月 1 日 04:00 去重，低优先级）
#
# 回滚：用 git 上一版脚本重跑本安装 + daemon-reload；禁用去重：
#   systemctl disable --now vpush-cicc-dedup.timer
set -euo pipefail

LIBDIR=/usr/local/lib/vpush-ima
HERE=$(cd "$(dirname "$0")" && pwd)

install -m 744 "$HERE/cicc-consistency.py"    "$LIBDIR/cicc-consistency.py"
install -m 744 "$HERE/cicc-status.py"         "$LIBDIR/cicc-status.py"
install -m 744 "$HERE/cicc-dispatch.py"       "$LIBDIR/cicc-dispatch.py"
install -m 744 "$HERE/cicc-incremental.py"    "$LIBDIR/cicc-incremental.py"
[ -f "$HERE/cicc_report_collector.py" ] && install -m 744 "$HERE/cicc_report_collector.py" /root/cicc/cicc_report_collector.py

cat > /etc/systemd/system/vpush-cicc-dedup.service <<'UNIT'
[Unit]
Description=V Push archive monthly dedup (hardlink)

[Service]
Type=oneshot
ExecStart=/usr/bin/nice -n 19 /usr/bin/python3 /root/cicc/pdf_dedup_hardlink.py --apply
UMask=0077
NoNewPrivileges=true
TimeoutStartSec=7200

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/vpush-cicc-dedup.timer <<'UNIT'
[Unit]
Description=V Push archive monthly dedup

[Timer]
OnCalendar=*-*-01 04:00:00 Asia/Shanghai
Persistent=true

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl restart vpush-cicc-dispatch.path
systemctl enable --now vpush-cicc-dedup.timer vpush-cicc-status.timer
echo "batch3 install done"
