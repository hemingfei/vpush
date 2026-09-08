"""入库繁转简。已是简体时接近恒等，不做繁体检测。"""
from zhconv import convert


def to_simplified(text: str | None) -> str:
    if not text:
        return text or ""
    return convert(text, "zh-cn")
