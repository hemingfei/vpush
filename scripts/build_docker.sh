#!/usr/bin/env bash
# 一键构建 Docker 镜像并导出为 tar
# 用法: bash scripts/build_docker.sh   (在仓库任意位置均可运行)
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> [1/3] 构建主镜像 vpush:latest ..."
docker build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple -t vpush:latest .

echo "==> [2/3] 构建镜像 vpush-waf-bot:latest ..."
docker build -t vpush-waf-bot:latest ./waf-bot

echo "==> [3/3] 导出镜像到 vpush-latest.tar ..."
docker save vpush:latest vpush-waf-bot:latest -o vpush-latest.tar

echo "==> 完成: $(ls -lh vpush-latest.tar | awk '{print $5, $9}')"
