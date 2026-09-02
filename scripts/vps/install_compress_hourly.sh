#!/bin/bash
# IMA PDF v3 每小时增量压缩 + 中金每日去水印/压缩 + 全站每月去重任务。
# 从仓库运行本脚本会同步部署 compressor、deduper、collector 和使用同一归档锁的 puller。
# 回滚：使用 /root/cicc/backup-compress-v3-* 恢复脚本和 unit。
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)

systemctl disable --now vpush-compress-monthly.timer 2>/dev/null || true
systemctl stop vpush-compress-monthly.service 2>/dev/null || true
systemctl disable --now vpush-compress-hourly.timer 2>/dev/null || true
systemctl stop vpush-compress-hourly.service 2>/dev/null || true
systemctl disable --now vpush-cicc-pdf-daily.timer 2>/dev/null || true
systemctl stop vpush-cicc-pdf-daily.service 2>/dev/null || true
systemctl disable --now vpush-cicc-dedup.timer 2>/dev/null || true
systemctl stop vpush-cicc-dedup.service 2>/dev/null || true

install -m 744 "$REPO_ROOT/scripts/cicc_report_collector.py" /root/cicc/cicc_report_collector.py
install -m 700 "$REPO_ROOT/scripts/pdf_backfill_compress.py" /root/cicc/pdf_backfill_compress.py
install -m 700 "$REPO_ROOT/scripts/pdf_dedup_hardlink.py" /root/cicc/pdf_dedup_hardlink.py
install -m 755 "$REPO_ROOT/scripts/vps/ima-puller.py" /usr/local/lib/vpush-ima/ima-puller.py
install -m 744 "$REPO_ROOT/scripts/vps/cicc-dispatch.py" /usr/local/lib/vpush-ima/cicc-dispatch.py
install -o 99 -g 100 -m 660 /dev/null /srv/vpush-ima/.vpush-pdf.lock
/usr/bin/python3 -m py_compile /root/cicc/cicc_report_collector.py \
  /root/cicc/pdf_backfill_compress.py /root/cicc/pdf_dedup_hardlink.py \
  /usr/local/lib/vpush-ima/ima-puller.py \
  /usr/local/lib/vpush-ima/cicc-dispatch.py
/usr/bin/python3 -c 'import fitz; assert hasattr(fitz.Document, "subset_fonts")'
systemctl restart vpush-ima-puller.service

cat > /etc/systemd/system/vpush-compress-hourly.service <<'UNIT'
[Unit]
Description=V Push hourly incremental PDF compression
ConditionPathExists=/root/cicc/pdf_backfill_compress.py

[Service]
Type=oneshot
ExecStart=/usr/bin/nice -n 19 /usr/bin/ionice -c2 -n7 /usr/bin/python3 /root/cicc/pdf_backfill_compress.py
UMask=0077
NoNewPrivileges=true
TimeoutStartSec=28800
UNIT

cat > /etc/systemd/system/vpush-compress-hourly.timer <<'UNIT'
[Unit]
Description=V Push hourly incremental PDF compression

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
UNIT

cat > /etc/systemd/system/vpush-cicc-pdf-daily.service <<'UNIT'
[Unit]
Description=V Push daily CICC PDF watermark removal and compression
ConditionPathExists=/srv/vpush-ima/local/cicc-research

[Service]
Type=oneshot
ExecStart=/usr/bin/nice -n 19 /usr/bin/ionice -c2 -n7 /usr/bin/python3 /root/cicc/pdf_backfill_compress.py --root /srv/vpush-ima/local/cicc-research --strip-watermark
UMask=0077
NoNewPrivileges=true
TimeoutStartSec=28800
UNIT

cat > /etc/systemd/system/vpush-cicc-pdf-daily.timer <<'UNIT'
[Unit]
Description=V Push daily CICC PDF watermark removal and compression

[Timer]
OnCalendar=*-*-* 06:15:00 Asia/Shanghai
Persistent=true

[Install]
WantedBy=timers.target
UNIT

cat > /etc/systemd/system/vpush-cicc-dedup.service <<'UNIT'
[Unit]
Description=V Push archive monthly PDF deduplication
ConditionPathExists=/root/cicc/pdf_dedup_hardlink.py

[Service]
Type=oneshot
ExecStart=/usr/bin/nice -n 19 /usr/bin/ionice -c2 -n7 /usr/bin/python3 /root/cicc/pdf_dedup_hardlink.py --apply
UMask=0077
NoNewPrivileges=true
TimeoutStartSec=7200
UNIT

cat > /etc/systemd/system/vpush-cicc-dedup.timer <<'UNIT'
[Unit]
Description=V Push archive monthly PDF deduplication

[Timer]
OnCalendar=*-*-01 04:10:00 Asia/Shanghai
Persistent=true

[Install]
WantedBy=timers.target
UNIT

rm -f /etc/systemd/system/vpush-compress-monthly.timer \
      /etc/systemd/system/vpush-compress-monthly.service
systemctl daemon-reload
systemctl restart vpush-cicc-dispatch.path 2>/dev/null || true
systemctl enable --now vpush-compress-hourly.timer vpush-cicc-pdf-daily.timer \
  vpush-cicc-dedup.timer
echo "v3 compressor, monthly deduper, puller lock, hourly timer, and CICC daily timer installed"
