"""研报文本兜底抽取：txt 缺失时用 pymupdf 取 PDF 前几页（评级/标的集中在首页）。"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PDF_MAX_PAGES = 4
_PDF_MAX_CHARS = 12000


def pdf_first_pages_text(pdf_path: Path, max_pages: int = _PDF_MAX_PAGES) -> str:
    """读 PDF 前 N 页文本；pymupdf 不可用或解析失败返回空串（调用方落 notext 行）。"""
    try:
        import fitz
    except ImportError:
        logger.warning("pymupdf 未安装，跳过 PDF 文本兜底抽取")
        return ""
    try:
        with fitz.open(pdf_path) as doc:
            pages = [doc[i].get_text() for i in range(min(max_pages, len(doc)))]
    except Exception as exc:  # noqa: BLE001 - 损坏/加密 PDF 统一降级
        logger.warning("PDF 文本抽取失败 %s: %s", pdf_path.name, exc)
        return ""
    return " ".join(" ".join(page.split()) for page in pages)[:_PDF_MAX_CHARS]
