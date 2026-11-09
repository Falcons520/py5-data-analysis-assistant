"""安全相关的纯函数：HTML 清洗、文件名校验。"""

from __future__ import annotations

import re

_BLOCK_TAGS = re.compile(
    r"<\s*(script|iframe|object|embed|link|meta|style|form)\b[^>]*>.*?<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_SELF_CLOSING_BAD = re.compile(
    r"<\s*(script|iframe|object|embed|link|meta|base)\b[^>]*/?>",
    re.IGNORECASE | re.DOTALL,
)
_EVENT_ATTR = re.compile(r"\son[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.IGNORECASE)
_DANGEROUS_URL = re.compile(
    r"(href|src)\s*=\s*(\"|')?\s*(javascript|vbscript|data:text/html)[^\"'\s>]*",
    re.IGNORECASE,
)
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def sanitize_html(html: str) -> str:
    """粗粒度白名单式清洗：仅用于渲染 LLM 生成的报告 HTML。

    浏览器端还会用 DOMParser 再清洗一次，这里是第一道防线。
    """
    if not html:
        return ""
    text = _CTRL.sub("", str(html))
    text = _BLOCK_TAGS.sub("", text)
    text = _SELF_CLOSING_BAD.sub("", text)
    text = _EVENT_ATTR.sub("", text)
    text = _DANGEROUS_URL.sub(r"\1=\"#\"", text)
    return text.strip()


def safe_filename(name: str, fallback: str = "report") -> str:
    """生成安全的下载文件名（去掉路径分隔符与控制字符）。"""
    name = _CTRL.sub("", str(name or "")).replace("\\", "_").replace("/", "_")
    name = re.sub(r"[\r\n\t]", " ", name).strip(" .")
    return name[:80] or fallback
