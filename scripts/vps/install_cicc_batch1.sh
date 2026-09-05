#!/bin/bash
# 知识库设置增强第一批：存储机侧安装（幂等）。
# 在存储 VPS 上执行：bash install_cicc_batch1.sh
#
# 变更：
#   1. 安装新版 cicc-status.py（status.json 增加 storage 节：磁盘/WG/NFS/统计/计划）
#   2. 安装新版 cicc-incremental.py（每小时 :05 tick + 门控：计划时间/当日已跑/占用跳过，
#      结果写 last_incr_summary.json 供通知）
#   3. vpush-cicc-incremental.timer：每日 03:00 → 每小时 :05（门控决定是否真跑），Persistent 保持
#   4. 新增 cicc-stats.py + vpush-cicc-stats.timer（每小时 :20，归档体量统计）
#   5. cicc-dispatch.py 增加 schedule 命令模式（应用设置页下发采集时间）
#
# 回滚：git checkout 旧版四脚本重跑本安装 + daemon-reload；incremental.timer 的 OnCalendar
# 改回 '*-*-* 03:00:00 Asia/Shanghai'。
set -euo pipefail

LIBDIR=/usr/local/lib/vpush-ima
HERE=$(cd "$(dirname "$0")" && pwd)

install -m 744 "$HERE/cicc-status.py"      "$LIBDIR/cicc-status.py"
install -m 744 "$HERE/cicc-incremental.py" "$LIBDIR/cicc-incremental.py"
install -m 744 "$HERE/cicc-stats.py"       "$LIBDIR/cicc-stats.py"
install -m 744 "$HERE/cicc-dispatch.py"    "$LIBDIR/cicc-dispatch.py"

cat > /etc/systemd/system/vpush-cicc-incremental.timer <<'UNIT'
[Unit]
Description=V Push CICC collector hourly gate tick

[Timer]
OnCalendar=*-*-* *:05:00 Asia/Shanghai
Persistent=true

[Install]
WantedBy=timers.target
UNIT

cat > /etc/systemd/system/vpush-cicc-dispatch.timer <<'UNIT'
[Unit]
Description=Retry pending V Push CICC commands

[Timer]
OnBootSec=1min
OnUnitActiveSec=1min
Unit=vpush-cicc-dispatch.service

[Install]
WantedBy=timers.target
UNIT

cat > /etc/systemd/system/vpush-cicc-dispatch.service <<'UNIT'
[Unit]
Description=V Push CICC collector command dispatcher

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/local/lib/vpush-ima/cicc-dispatch.py
UMask=0077
NoNewPrivileges=true
# 全量采集由 dispatch 同步等待，以真实退出码写结果。
TimeoutStartSec=46800

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/vpush-cicc-incremental.service <<'UNIT'
[Unit]
Description=V Push CICC collector daily incremental (gated)

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/local/lib/vpush-ima/cicc-incremental.py
UMask=0077
NoNewPrivileges=true
TimeoutStartSec=1800

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/vpush-cicc-stats.service <<'UNIT'
[Unit]
Description=V Push CICC archive stats (hourly)

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/local/lib/vpush-ima/cicc-stats.py
UMask=0077
NoNewPrivileges=true
TimeoutStartSec=600

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/vpush-cicc-stats.timer <<'UNIT'
[Unit]
Description=V Push CICC archive stats hourly

[Timer]
OnCalendar=*-*-* *:20:00 Asia/Shanghai
Persistent=true

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl restart vpush-cicc-incremental.timer
systemctl enable --now vpush-cicc-stats.timer vpush-cicc-status.timer \
  vpush-cicc-dispatch.path vpush-cicc-dispatch.timer
echo "install done"
