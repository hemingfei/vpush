#!/usr/bin/env python3
"""中金点睛研报批量采集 → 存储机本地库（/srv/vpush-ima/local/<slug>/）。

用法（存储 VPS 上）：
  python3 cicc_report_collector.py --days 30            # 最近30天
  python3 cicc_report_collector.py --all                # 全量（分页拉完为止）
  python3 cicc_report_collector.py --categories 宏观经济,市场策略 --days 7
  python3 cicc_report_collector.py --self-test          # 离线自检

登录态：/root/cicc/cookies.txt（一行原始 Cookie 头），chmod 600。
目录契约见 docs/superpowers/specs/2026-08-29-local-storage-library-mount-design.md：
  local/cicc-research/.vpush-local-library.json
  local/cicc-research/.vpush-local-meta.jsonl   # 列表摘要/标签 sidecar，扫描器按 *_<id>.pdf 匹配
  local/cicc-research/<品类>/<MMDD>/<中文原名>_<id>.pdf
  属主 99:100。
"""

import argparse
import fcntl
import http.client
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = "https://www.research.cicc.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
REFERER = BASE + "/zh_CN/reportList"
CHOWN_UID, CHOWN_GID = 99, 100
TZ_BJ = timezone(timedelta(hours=8))
PAGE_SIZE = 50
SLEEP_PAGE, SLEEP_DL = 0.6, 0.25
MAX_PAGES = 2000
PAUSED_FILE = "/srv/vpush-ima/local/.cicc/paused.json"


def write_paused(reason: str, detail: str) -> None:
    """熔断前尽力记录原因（quota=配额满 / auth=登录失效），供状态展示与增量门控。
    脚本可能以非 root 跑（目录属主 99:100），写失败静默忽略，不改变退出行为。"""
    try:
        p = Path(PAUSED_FILE)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f".paused.tmp.{os.getpid()}")
        tmp.write_text(json.dumps({"reason": reason, "ts": int(time.time()),
                                   "detail": detail[:200]}, ensure_ascii=False),
                       encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        pass

# 网页一级品类 → 库 slug（规格约束 slug 仅小写字母数字连字符）
SLUG_MAP = {
    "宏观经济": "cicc-macro",
    "市场策略": "cicc-strategy",
    "全球研究": "cicc-global",
    "行业研究": "cicc-industry",
    "公司研究": "cicc-company",
    "量化及ESG": "cicc-quant-esg",
    "大宗商品": "cicc-commodity",
    "外汇研究": "cicc-fx",
    "固定收益": "cicc-bond",
    "中金研究院": "cicc-institute",
    "其他": "cicc-other",
}

DEFAULT_BODY = {
    "input": "", "searchField": "titleSeg",
    "analyst": {"value": "", "name": ""}, "author": [],
    "pubTimeStart": None, "pubTimeEnd": None,
    "stock": {"value": "", "name": ""},
    "portalCategoryId": "", "subPortalCategoryId": {},
    "industriesIds": "", "subIndustriesIds": {},
    "reportNumCode": "", "level": [""], "levelChange": [""],
    "cusPageRange": "", "currencyIds": "", "commodityType": "",
    "page": 1, "size": PAGE_SIZE,
    "authorId": "", "secCode": "", "minPageCount": "", "maxPageCount": "",
}


def x_time() -> str:
    u = int(time.time() * 1000) // 10
    return str(u) + str(u % 97).zfill(2)


class Session:
    """同 host keep-alive 连接：每篇 detail+fetchPdf 两次请求复用一次 TLS 握手。
    连接被服务端关闭/异常时重建并重试。"""

    def __init__(self, cookie: str):
        self.cookie = cookie.strip().rstrip(";")
        self.conn: http.client.HTTPSConnection | None = None

    def request(self, path: str, *, body: dict | None = None,
                raw: bool = False, tries: int = 3) -> bytes | dict:
        headers = {"User-Agent": UA, "Cookie": self.cookie, "X-Time": x_time(),
                   "Referer": REFERER, "Origin": BASE}
        payload_body = None
        if body is not None:
            payload_body = json.dumps(body, ensure_ascii=False).encode()
            headers["Content-Type"] = "application/json"
        last_err: Exception = RuntimeError("unreachable")
        for attempt in range(1, tries + 1):
            try:
                if self.conn is None:
                    self.conn = http.client.HTTPSConnection(BASE.removeprefix("https://"), timeout=60)
                self.conn.request("POST" if body is not None else "GET", path,
                                  body=payload_body, headers=headers)
                resp = self.conn.getresponse()
                payload = resp.read()
                if resp.status != 200:
                    detail = payload[:200].decode("utf-8", "replace")
                    if resp.status in (401, 412) or "40010" in detail:
                        write_paused("auth", f"HTTP {resp.status} 登录态失效")
                        sys.exit(f"登录态失效（HTTP {resp.status}）：请更新 Cookie 后重跑。")
                    if "400013" in detail:
                        write_paused("quota", "code 400013 本月配额已满")
                        sys.exit("本月研报下载数量已达上限（code 400013）：等配额重置后重跑即可续传。")
                    raise RuntimeError(f"HTTP {resp.status} {detail}")
                if raw:
                    return payload
                obj = json.loads(payload)
                code = obj.get("code")
                if code == 0:
                    return obj
                if code == 40010:
                    write_paused("auth", "code 40010 登录态失效")
                    sys.exit("登录态失效（code 40010）：请更新 Cookie 文件后重跑。")
                if code == 400013:
                    write_paused("quota", "code 400013 本月配额已满")
                    sys.exit("本月研报下载数量已达上限（code 400013）：等配额重置后重跑即可续传。")
                raise RuntimeError(f"api code={code} msg={obj.get('msg') or obj.get('desc')}")
            except (http.client.HTTPException, OSError, TimeoutError, json.JSONDecodeError) as e:
                self.conn = None  # 连接失效：重建后重试
                last_err = e
            if attempt < tries:
                time.sleep(2 * attempt)
        raise last_err


def filter_by_keywords(items: list[dict], keywords: list[str]) -> list[dict]:
    """标题关键词白名单：任一关键词（大小写不敏感）命中即保留；空白名单=全部保留。"""
    kw = [k.strip().lower() for k in keywords if k and k.strip()]
    if not kw:
        return items
    return [it for it in items
            if any(k in str(it.get("title") or "").lower() for k in kw)]


def sanitize_title(title: str) -> str:
    title = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", title)
    title = re.sub(r"\s+", " ", title).strip().strip(".")
    return title


def fit_bytes(name: str, budget: int) -> str:
    raw = name.encode("utf-8")
    if len(raw) <= budget:
        return name
    cut = budget
    while cut > 0 and (raw[cut] & 0xC0) == 0x80:
        cut -= 1
    return raw[:cut].decode("utf-8", "ignore")


def day_dir(publish_time: str) -> str:
    dt = datetime.fromisoformat(publish_time.replace("Z", "+00:00"))
    return (dt.astimezone(TZ_BJ)).strftime("%m%d")


LIB_SLUG, LIB_NAME = "cicc-research", "中金点睛"
SIDECAR_NAME = ".vpush-local-meta.jsonl"


def publish_date(publish_time: str) -> str:
    """列表 publishTime → 北京日期 YYYY-MM-DD；非法则空串。"""
    raw = str(publish_time or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.astimezone(TZ_BJ).strftime("%Y-%m-%d")
    except ValueError:
        day = raw[:10]
        return day if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) else ""


def category_id_names(param: dict) -> dict:
    """param.treeData / industriesData 的 id→中文名（含子节点）。"""
    id_name: dict = {}
    for node in list(param.get("treeData") or []) + list(param.get("industriesData") or []):
        if not isinstance(node, dict):
            continue
        nid, nname = node.get("id"), node.get("name")
        if nid is not None and nname:
            id_name[nid] = nname
            id_name[str(nid)] = nname
        for ch in node.get("children") or []:
            if not isinstance(ch, dict):
                continue
            cid, cname = ch.get("id"), ch.get("name")
            if cid is not None and cname:
                id_name[cid] = cname
                id_name[str(cid)] = cname
    return id_name


def sidecar_row(item: dict, id_name: dict, cat_name: str = "") -> dict:
    """列表项 → sidecar 一行，字段对齐 cicc_meta_backfill / 本地库规格 §11。"""
    tags: list[str] = []
    extra = list(item.get("documentLabels") or [])
    for raw in [item.get("reportType"), cat_name, *extra]:
        tag = str(raw).strip() if raw else ""
        if tag and tag not in tags:
            tags.append(tag)
    for pid in item.get("portalCategoryIds") or []:
        name = id_name.get(pid) or id_name.get(str(pid))
        if name and name not in tags:
            tags.append(name)
    authors = []
    for analyst in item.get("analysts") or []:
        if isinstance(analyst, dict) and analyst.get("name"):
            authors.append(str(analyst["name"]).strip())
        elif isinstance(analyst, str) and analyst.strip():
            authors.append(analyst.strip())
    day = publish_date(item.get("publishTime") or "")
    return {
        "id": str(item.get("id") or "").strip(),
        "title": str(item.get("title") or ""),
        "summary": str(item.get("summary") or "")[:2000],
        "tags": tags[:5],
        "day": day.replace("-", "")[4:] if len(day) >= 10 else "unknown",
        "publish": day,
        "authors": " ".join(authors),
    }


def load_sidecar(path: Path) -> dict:
    rows: dict = {}
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return rows
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = str(row.get("id") or "").strip() if isinstance(row, dict) else ""
        if rid:
            rows[rid] = row
    return rows


def merge_sidecar(path: Path, updates: dict, *, fix_owner: bool = False) -> int:
    """把本轮 upsert 合并进 sidecar（文件锁，多进程分片不会互相覆盖）。"""
    if not updates:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(".vpush-local-meta.lock")
    with open(lock_path, "a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        rows = load_sidecar(path)
        rows.update(updates)
        tmp = path.with_name(f".vpush-local-meta.jsonl.tmp.{os.getpid()}")
        tmp.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows.values()),
            encoding="utf-8",
        )
        os.replace(tmp, path)
        if fix_owner:
            os.chown(path, CHOWN_UID, CHOWN_GID)
            os.chmod(path, 0o640)
            try:
                os.chown(lock_path, CHOWN_UID, CHOWN_GID)
            except OSError:
                pass
        return len(rows)


def target_path(root: Path, cat_name: str, publish_time: str, title: str, rid: int) -> Path:
    """单库布局：root/cicc-research/<品类名>/<MMDD>/<中文名>_<id>.pdf"""
    name = fit_bytes(sanitize_title(title), 200 - len(f"_{rid}")) + f"_{rid}.pdf"
    return root / LIB_SLUG / cat_name / day_dir(publish_time) / name


def setup_library(root: Path, slug: str, name: str, *, fix_owner: bool) -> None:
    d = root / slug
    d.mkdir(parents=True, exist_ok=True)
    marker = d / ".vpush-local-library.json"
    if not marker.exists():
        marker.write_text(json.dumps({
            "name": name, "enabled": False, "tags": ["中金研报"],
        }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if fix_owner:
        for p in [d, marker]:
            os.chown(p, CHOWN_UID, CHOWN_GID)
        os.chmod(d, 0o750)
        os.chmod(marker, 0o640)


def fetch_param(sess: Session) -> dict:
    return sess.request("/reports/api/v3/param")["data"]


def fetch_categories(sess: Session) -> list[dict]:
    return fetch_param(sess)["treeData"]


def list_page(sess: Session, cat_id: int, page: int, start: str | None, end: str | None) -> dict:
    body = dict(DEFAULT_BODY)
    body["portalCategoryId"] = str(cat_id)
    body["pubTimeStart"] = start
    body["pubTimeEnd"] = end
    body["page"] = page
    return sess.request("/reports/api/v3/page", body=body)["data"]


def viewer_pdf(sess: Session, rid: int) -> bytes:
    """在线阅读流：detail → signatureUrl(/v3/fetchPdf/<token>)，不计入月度下载配额
    （2026-09 实测：写不写 download/list 记录 309→309，内容与 download 版逐页一致且
    无下载水印）。detail 接口本身是读操作，不占配额。"""
    data = sess.request(f"/reports/api/v3/detail?id={rid}")["data"]
    sig = data.get("signatureUrl")
    if not sig:
        raise RuntimeError(f"detail 未返回 signatureUrl（id={rid}）")
    path = sig.replace(BASE, "")
    payload = sess.request(path, raw=True, tries=2)
    if not payload.startswith(b"%PDF"):
        raise RuntimeError("fetchPdf 非 PDF 响应: " + payload[:200].decode("utf-8", "replace"))
    return payload


def download_pdf(sess: Session, rid: int) -> bytes:
    """配额版下载（默认不用）：GET /v3/download/<id>，计入月度 300 篇配额（400013）。"""
    payload = sess.request(f"/reports/api/v3/download/{rid}", raw=True, tries=2)
    if not payload.startswith(b"%PDF"):
        text = payload[:200].decode("utf-8", "replace")
        if b"400013" in payload[:200]:
            write_paused("quota", "code 400013 本月配额已满")
            sys.exit("本月研报下载数量已达上限（code 400013）：等配额重置后重跑即可续传。")
        raise RuntimeError("非 PDF 响应: " + text)
    return payload


# 中金下载时 iTextSharp 注入的水印贴图尺寸：756x192=身份贴片（*先伟 **邮箱 + 时间戳，
# 每页平铺约 90 次），380x138=页中大灰色 CICC logo。识别按尺寸（资源名跨页会变）。
WM_SIZES = {(756, 192), (380, 138)}
_wm_warned = False


def strip_watermark(payload: bytes) -> bytes:
    """内存中去水印：抹掉水印图的 Do 绘制指令并清资源引用。压缩纯无损
    （deflate 重压/对象流/垃圾回收，不重采样图片；实测>300ppi图仅占体积~9%，
    有损降采样不划算，维持不动）。没剥水印且重压不省空间 → 保留原文件。
    任何异常返回原文（宁带水印不丢文件）；未装 pymupdf 时原样跳过。"""
    global _wm_warned
    try:
        import fitz
    except ImportError:
        if not _wm_warned:
            print("WARN: 未装 python3-fitz/pymupdf，本次不去水印", file=sys.stderr)
            _wm_warned = True
        return payload
    try:
        doc = fitz.open(stream=payload, filetype="pdf")
        stripped = False
        for page in doc:
            wm = [img for img in page.get_images(full=True)
                  if (img[2], img[3]) in WM_SIZES]
            if not wm:
                continue
            for xref in page.get_contents():  # 逐流处理：只改写含水印指令的流，避免全页重排膨胀
                cont = doc.xref_stream(xref)
                hit = False
                for img in wm:
                    pat = (f"/{img[7]} Do").encode("latin-1")
                    if pat in cont:
                        cont = cont.replace(pat, b"n ")  # 空操作，保持 q/Q 平衡
                        hit = True
                if hit:
                    doc.update_stream(xref, cont)
                    stripped = True
            for img in wm:  # 清空图流（含 smask）：不动 Resources dict，顺带抹掉水印字节本体
                doc.update_stream(img[0], b"")
                if img[1]:
                    doc.update_stream(img[1], b"")
                stripped = True
        out = doc.tobytes(garbage=4, deflate=True, use_objstms=1)
        return out if (stripped or len(out) < len(payload)) else payload
    except Exception as e:  # noqa: BLE001 — 去水印失败不阻断采集
        print(f"WARN: 去水印失败，保留原文件: {e}", file=sys.stderr)
        return payload


COMPRESS_RATIO = 0.90  # 压缩后体积低于原件 90% 才采用；已优化的 PDF 压不动，自动跳过（幂等）
_gs_warned = False


def pdf_equivalent(a: bytes, b: bytes) -> bool:
    """页数一致且逐页文本层一致（忽略空白）才认为内容等价。"""
    try:
        import fitz
        da, db = fitz.open(stream=a, filetype="pdf"), fitz.open(stream=b, filetype="pdf")
        if len(da) != len(db):
            return False
        return all(re.sub(r"\s+", "", pa.get_text()) == re.sub(r"\s+", "", pb.get_text())
                   for pa, pb in zip(da, db))
    except Exception:
        return False


def compress_pdf(data: bytes) -> bytes:
    """gs /prepress（最高品质，300dpi 上限）条件压缩：输出更小且内容等价才采用，
    否则原样返回。已压缩/优化的文件压不动 → 自动跳过，重复调用幂等。
    未装 ghostscript 或任何异常均返回原文，不阻断采集。"""
    global _gs_warned
    if not data.startswith(b"%PDF"):
        return data
    gs = shutil.which("gs")
    if not gs:
        if not _gs_warned:
            print("WARN: 未装 ghostscript，跳过压缩", file=sys.stderr)
            _gs_warned = True
        return data
    try:
        with tempfile.TemporaryDirectory() as td:
            src, out = os.path.join(td, "s.pdf"), os.path.join(td, "o.pdf")
            with open(src, "wb") as f:
                f.write(data)
            r = subprocess.run(
                [gs, "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.7",
                 "-dPDFSETTINGS=/prepress", "-dAutoRotatePages=/None",
                 "-dNOPAUSE", "-dQUIET", "-dBATCH", f"-sOutputFile={out}", src],
                capture_output=True, timeout=600)
            if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) == 0:
                return data
            with open(out, "rb") as f:
                new = f.read()
    except Exception:  # noqa: BLE001 — 压缩失败不阻断采集
        return data
    if len(new) >= len(data) * COMPRESS_RATIO or not pdf_equivalent(data, new):
        return data
    return new


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cookie-file", default="/root/cicc/cookies.txt")
    ap.add_argument("--root", default="/srv/vpush-ima/local")
    ap.add_argument("--days", type=int, default=0, help="最近 N 天（含今天），0=不限")
    ap.add_argument("--since", default="", help="起始日期 YYYY-MM-DD（如 2026-01-01 采今年），优先于 --days")
    ap.add_argument("--all", action="store_true", help="全量，不按日期过滤")
    ap.add_argument("--categories", default="", help="逗号分隔的一级品类名，默认全部")
    ap.add_argument("--keywords", default="", help="逗号分隔的标题关键词白名单，默认不过滤")
    ap.add_argument("--limit", type=int, default=0, help="本次最多下载多少个 PDF（调试用）")
    ap.add_argument("--endpoint", choices=["viewer", "download"], default="viewer",
                    help="取 PDF 路径：viewer=在线阅读流 fetchPdf（不计月度配额，默认）；download=旧下载接口（计 300/月配额）")
    ap.add_argument("--page-start", type=int, default=1,
                    help="每品类从第几页开始列（同品类拆多进程对跑用）")
    ap.add_argument("--dry-run", action="store_true", help="只列清单不下载")
    ap.add_argument("--compress", action="store_true",
                    help="下载时同步 gs /prepress 压缩（1核机上单篇可达几十秒，默认关；推荐采完后用 "
                         "pdf_backfill_compress.py --root /srv/vpush-ima/local 低优先级回刷）")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        assert x_time().isdigit() and len(x_time()) >= 13
        assert sanitize_title('A/B：C"今年的<报告>') == "A B：C 今年的 报告"  # 全角保留，非法字符换空格
        assert fit_bytes("中" * 300, 20).encode().__len__() <= 20
        assert day_dir("2026-08-29T12:43:03Z") == "0829"  # UTC+8
        assert day_dir("2026-08-29T17:43:03Z") == "0830"  # 跨日归北京日期
        p = target_path(Path("/x"), "宏观经济", "2026-08-01T00:00:00Z", "标题/1", 42)
        assert str(p) == "/x/cicc-research/宏观经济/0801/标题 1_42.pdf", str(p)
        row = sidecar_row({
            "id": 42,
            "title": "宁德时代深度",
            "summary": "动力电池",
            "reportType": "深度报告",
            "documentLabels": ["新能源"],
            "portalCategoryIds": [7],
            "publishTime": "2026-08-29T17:43:03Z",
            "analysts": [{"name": "张三"}],
        }, {7: "电力设备"}, "公司研究")
        assert row["id"] == "42"
        assert row["publish"] == "2026-08-30"  # UTC 17:43 → 北京 0830
        assert row["day"] == "0830"
        assert row["tags"] == ["深度报告", "公司研究", "新能源", "电力设备"]
        assert row["authors"] == "张三"
        assert row["summary"] == "动力电池"
        try:
            import fitz
        except ImportError:
            fitz = None
        if fitz:  # 去水印：造一个只含水印尺寸图的 PDF，断言渲染后无任何可见像素
            d = fitz.open()
            pg = d.new_page()
            px = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 756, 192))
            px.set_rect(px.irect, (0, 0, 0))  # 黑块，若未剥离则渲染必非全白
            pg.insert_image(fitz.Rect(0, 0, 378, 96), pixmap=px)
            buf = io.BytesIO()
            d.save(buf)
            out = fitz.open(stream=strip_watermark(buf.getvalue()), filetype="pdf")
            assert len(out) == 1
            pix = out[0].get_pixmap(dpi=72)
            assert set(pix.samples) == {255}, "水印未被剥离"
            # 内容等价判断：同文本等价，异文本不等价
            assert pdf_equivalent(buf.getvalue(), buf.getvalue())
            d2 = fitz.open()
            pg2 = d2.new_page()
            pg2.insert_text((72, 72), "different")
            b2 = io.BytesIO()
            d2.save(b2)
            assert not pdf_equivalent(buf.getvalue(), b2.getvalue())
        assert compress_pdf(b"not a pdf") == b"not a pdf"  # 非 PDF 原样返回
        print("self-test ok")
        return

    cookie_path = Path(args.cookie_file)
    if not cookie_path.exists():
        sys.exit(f"Cookie 文件不存在: {cookie_path}")
    sess = Session(cookie_path.read_text(encoding="utf-8"))
    root = Path(args.root)
    fix_owner = os.geteuid() == 0 and str(root) == "/srv/vpush-ima/local"
    if fix_owner:
        root.mkdir(parents=True, exist_ok=True)
        os.chown(root, CHOWN_UID, CHOWN_GID)
        os.chmod(root, 0o750)

    wanted = [c.strip() for c in args.categories.split(",") if c.strip()]
    param = fetch_param(sess)  # 列表接口是读操作：能成功即登录态有效
    all_cats = param.get("treeData") or []
    id_name = category_id_names(param)
    try:
        os.remove(PAUSED_FILE)  # 新一轮跑起来了：清掉上次的熔断标记（再熔断会重写）
    except OSError:
        pass
    if wanted:
        cats = [c for c in all_cats if c["name"] in wanted]
        missing = set(wanted) - {c["name"] for c in cats}
        if missing:
            sys.exit(f"未知品类: {missing}；可选: {[c['name'] for c in all_cats]}")
    else:
        cats = all_cats

    end = date.today().strftime("%Y-%m-%d")
    start = args.since or ((date.today() - timedelta(days=args.days - 1)).strftime("%Y-%m-%d") if args.days else None)

    stats = {"downloaded": 0, "skipped": 0, "failed": 0}
    stop = False
    # 幂等只靠磁盘文件名（含报告 id，唯一）；无 state 文件，多进程并行无竞态

    setup_library(root, LIB_SLUG, LIB_NAME, fix_owner=fix_owner)
    sidecar_path = root / LIB_SLUG / SIDECAR_NAME
    pending_meta: dict = {}

    def flush_sidecar() -> None:
        nonlocal pending_meta
        if pending_meta:
            merge_sidecar(sidecar_path, pending_meta, fix_owner=fix_owner)
            pending_meta = {}

    for cat in cats:
        name = cat["name"]
        if stop:
            break
        page, total_seen = args.page_start, 0
        while True:
            data = list_page(sess, cat["id"], page, start, None if args.all else end)
            items = filter_by_keywords(
                data.get("content") or [],
                [k for k in (args.keywords or "").split(",") if k.strip()],
            )
            if page == 1:
                print(f"[{name}] total={data.get('totalElements')} pages={data.get('totalPages')}")
            if not items:
                break
            for it in items:
                total_seen += 1
                rid = it["id"]
                if args.limit and stats["downloaded"] >= args.limit:
                    stop = True
                    break
                tp = target_path(root, name, it["publishTime"], it["title"], rid)
                row = sidecar_row(it, id_name, name)
                if row["id"]:
                    pending_meta[row["id"]] = row
                    if len(pending_meta) >= 20:
                        flush_sidecar()
                if tp.exists():
                    stats["skipped"] += 1
                    continue
                if args.dry_run:
                    print(f"  DRY {tp.relative_to(root)}")
                    continue
                try:
                    fetch = download_pdf if args.endpoint == "download" else viewer_pdf
                    payload = strip_watermark(fetch(sess, rid))  # 无损去水印，毫秒级
                    if args.compress:
                        payload = compress_pdf(payload)
                    tp.parent.mkdir(parents=True, exist_ok=True)
                    if fix_owner:
                        os.chown(tp.parent, CHOWN_UID, CHOWN_GID)
                        os.chmod(tp.parent, 0o750)
                    tp.write_bytes(payload)
                    if fix_owner:
                        os.chown(tp, CHOWN_UID, CHOWN_GID)
                        os.chmod(tp, 0o640)
                    stats["downloaded"] += 1
                    if stats["downloaded"] % 20 == 0:
                        print(f"  ... {stats['downloaded']} 下载 / {stats['skipped']} 已存在 / {stats['failed']} 失败")
                except Exception as e:  # noqa: BLE001 — 单个失败不中断整批
                    stats["failed"] += 1
                    print(f"  FAIL {rid} {it['title'][:40]}: {e}", file=sys.stderr)
                time.sleep(SLEEP_DL)
            if stop or page >= MAX_PAGES or len(items) < PAGE_SIZE:
                break
            page += 1
            time.sleep(SLEEP_PAGE)
        flush_sidecar()
        print(f"[{name}] 列出 {total_seen} 篇" + ("（中止）" if stop else ""))

    flush_sidecar()
    print(f"完成：下载 {stats['downloaded']}，已存在跳过 {stats['skipped']}，失败 {stats['failed']}")


if __name__ == "__main__":
    main()
