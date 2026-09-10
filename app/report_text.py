"""研报文本兜底抽取：txt 缺失时取 PDF 前几页（评级/标的集中在首页）。"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PDF_MAX_PAGES = 4
_PDF_MAX_CHARS = 12000


def usable_report_text(text: str) -> str:
    """Return extracted text unless it is a short broken-font mapping.

    Some broker PDFs contain no usable font resources; pypdf then returns a few
    long alphanumeric tokens that are not report content. Those tokens should
    not be sent to the LLM as if they were readable text.
    """
    normalized = " ".join((text or "").split())
    if not normalized:
        return ""
    words = normalized.split(" ")
    if len(normalized) <= 200 and max((len(word) for word in words), default=0) >= 18:
        return ""
    return normalized


def pdf_first_pages_text(pdf_path: Path, max_pages: int = _PDF_MAX_PAGES) -> str:
    """用项目既有的 pypdf 读取 PDF 前 N 页；解析失败返回空串。"""
    try:
        from pypdf import PdfReader

        reader = PdfReader(pdf_path)
        pages = [reader.pages[i].extract_text() or "" for i in range(min(max_pages, len(reader.pages)))]
    except Exception as exc:  # noqa: BLE001 - 损坏/加密 PDF 统一降级
        logger.warning("PDF 文本抽取失败 %s: %s", pdf_path.name, exc)
        return ""
    return " ".join(" ".join(page.split()) for page in pages)[:_PDF_MAX_CHARS]
