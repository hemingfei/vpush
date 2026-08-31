#!/bin/bash
# 月度增量压缩 timer（存储 VPS）：每月 1 日 08:00 跑一次 pdf_backfill_compress.py。
# - 断点续跑：state 里已处理过的文件跳过，只压新增/未处理文件（投行原版压不动会被
#   90% 阈值自动跳过，属设计内）
# - 排除 local/（中金库已有采集内压缩，且用户已叫停中金回刷）
# - 低优先级（nice+ionice 已在脚本内/ExecStart）
# 回滚：systemctl disable --now vpush-compress-monthly.timer && rm 单元文件
set -euo pipefail

cat > /etc/systemd/system/vpush-compress-monthly.service <<'UNIT'
[Unit]
Description=V Push monthly incremental PDF compression

[Service]
Type=oneshot
ExecStart=/usr/bin/nice -n 19 /usr/bin/ionice -c2 -n7 /usr/bin/python3 /root/cicc/pdf_backfill_compress.py
UMask=0077
NoNewPrivileges=true
TimeoutStartSec=28800

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/vpush-compress-monthly.timer <<'UNIT'
[Unit]
Description=V Push monthly incremental compression

[Timer]
OnCalendar=*-*-01 08:00:00 Asia/Shanghai
Persistent=true

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now vpush-compress-monthly.timer
echo "monthly compress timer installed"
