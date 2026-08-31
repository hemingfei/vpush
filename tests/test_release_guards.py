"""发版哨兵：关键修复的标记断言，防止发版提交带过期工作副本把修复覆盖掉。

背景（2026-08-30 审计）：v1.12.95 曾用过期 app.js/style.css 发版，静默覆盖了
d77ca9a 的两个前端修复。本文件把每项关键修复的「指纹字符串」固化为断言——
任何会话若用过期副本发版，CI 的 test job（docker-publish.yml，镜像构建 needs: test）
会在这里变红，镜像不发布。

维护约定：
- 新增关键修复时，在这里加一行标记（注明来源提交/审计项）；
- 一个修复被「更优方案」有意取代时，更新对应标记为新方案的指纹，不要直接删断言。
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

# (文件, 必须存在的指纹字符串, 修复说明)
SENTINELS = [
    # —— 审计修复批次（fix/knowledge-audit-p1，2026-08-30）——
    ("app/static/app.js", "data-ll-edit", "审计F1：本地库卡片点击改事件委托，去内联 onclick 注入面"),
    ("app/static/app.js", "_scanInFlight", "审计F2：本地库扫描中状态不被轮询重渲染击穿"),
    ("app/static/app.js", "fmtImaDayShort(item.sort_date || item.day)", "跨年日期：行卡片按真实发布日期展示"),
    # —— 本地库挂载（feat/local-library-mount，2026-08-30）——
    ("app/ima_documents.py", "def scan_local_libraries", "本地库扫描器存在"),
    ("app/ima_documents.py", "drop_duplicate_copies", "审计B2：增量同步「-副本」去重进读模型"),
    ("app/ima_documents.py", "def ima_sort_date", "跨年排序键（本地库 pub_date / IMA 年份补全）"),
    ("scripts/cicc_report_collector.py", "def strip_watermark", "采集管道去水印（Do 置空+清图流）——注意在采集脚本而非 app 包"),
    ("app/db.py", "sort_date", "读模型跨年排序列"),
    # —— 中金研报 UI（v1.12.96/97，2026-08-30）——
    ("app/static/app.js", "is-clamped", "摘要超长 3 行钳制 + 展开按钮"),
    ("app/static/style.css", ".ima-reader-abstract.is-clamped:not(.is-expanded)", "摘要钳制样式"),
    ("app/static/style.css", "min-height: 220px", "阅读器 PDF 预览区最低高度，不被长摘要压没"),
]


def test_release_sentinels_present():
    """所有关键修复指纹必须在位；缺失=发版副本过期，覆盖了已有修复。"""
    missing = []
    cache: dict[str, str] = {}
    for rel, marker, why in SENTINELS:
        if rel not in cache:
            path = ROOT / rel
            assert path.exists(), f"被审计文件不存在: {rel}"
            cache[rel] = path.read_text(encoding="utf-8")
        if marker not in cache[rel]:
            missing.append(f"{rel} 缺少标记 [{marker}]（{why}）")
    assert not missing, (
        "工作副本疑似过期，发版会覆盖以下已上线修复：\n" + "\n".join(missing)
        + "\n如为有意重构，请同步更新 tests/test_release_guards.py 的哨兵标记。"
    )
# —— 存储健康与采集设置批次（feat/kb-settings-batch1，2026-08-30）——
SENTINELS += [
    ("app/cicc_alerts.py", "def evaluate_alerts", "存储磁盘/状态阈值告警评估"),
    ("app/cicc_alerts.py", "def maybe_check_cicc", "告警与增量通知调度入口"),
    ("scripts/vps/cicc-incremental.py", "def should_run", "增量门控：计划时间/当日已跑"),
    ("scripts/vps/cicc-dispatch.py", '"schedule"', "命令通道支持下发采集时间"),
    ("app/static/app.js", "ima-storage-health", "存储页签健康总览面板"),
]

# —— 知识库设置增强第二批（feat/kb-settings-batch2，2026-08-30）——
SENTINELS += [
    ("scripts/cicc_report_collector.py", "def write_paused", "熔断前写 paused.json（quota/auth）"),
    ("scripts/cicc_report_collector.py", "def sidecar_row", "增量采集写入 sidecar 摘要/标签"),
    ("scripts/cicc_report_collector.py", "def merge_sidecar", "sidecar 文件锁合并，多进程不互相覆盖"),
    ("scripts/vps/cicc-status.py", '"paused"', "status 合并 paused.json 熔断状态"),
    ("scripts/vps/cicc-status.py", "def backup_section", "status 增加 backup 节（诚实呈现未配置）"),
    ("scripts/vps/cicc-incremental.py", "def paused_skip", "增量门控：auth 熔断 48h 内跳过"),
    ("scripts/vps/cicc-dispatch.py", '"settings"', "命令通道支持品类定向 settings"),
    ("scripts/vps/cicc-dispatch.py", '"backup"', "命令通道支持触发 restic 备份（替换死信请求文件）"),
    ("app/api.py", "cicc-categories", "品类定向 GET/PUT 端点"),
    ("app/cicc_alerts.py", "def paused_alert", "熔断告警文案（quota/auth 区分）"),
    ("app/static/app.js", "saveCiccCategories", "中金页签品类定向多选保存"),
    ("app/static/app.js", "备份未生效", "存储页签诚实展示备份未配置"),
]
# —— 知识库设置增强第三批（feat/kb-settings-batch2 后续，2026-08-30）——
SENTINELS += [
    ("app/static/app.js", "runStorageConsistency", "存储页签一致性体检入口"),
    ("app/static/app.js", "runStorageDedup", "去重手动触发入口"),
    ("app/static/app.js", "cicc-keywords", "标题关键词白名单输入"),
    ("app/knowledge_notify.py", "def maybe_notify_knowledge_keywords", "研报关键词合并推送"),
    ("app/static/app.js", "匹配研报库", "设置页研报匹配开关"),
    ("scripts/vps/cicc-consistency.py", "def main", "本地库一致性体检脚本"),
    ("scripts/vps/cicc-dispatch.py", "consistency", "一致性命令模式"),
]
