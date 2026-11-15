"""排版：把中文快讯纯文本转成公众号风格 HTML。

移植自 AIMedia 的 article-text.cjs（articleBlocks 分段）+ articleHtml 模板思路。
微信公众号只吃内联样式，所以全部样式写在标签 style 里。
"""
from __future__ import annotations

import html
import re


# ---------- 去频道推广尾巴 ----------
# 只从「末尾」逐行剥离推广/引流行，避免误删正文里偶然出现的词
PROMO_PATTERNS = [
    r"订阅[^\n]*(?:频道|曝光|群)",
    r"关注[^\n]*(?:频道|曝光|公众号)",
    r"投稿[^\n]{0,8}[:：]?\s*@?\w+",
    r"商务合作\s*[:：]",
    r"合作\s*[:：]\s*@\w+",
    r"t\.me/[A-Za-z0-9_]+",
    r"^[➡️👉🔗📢😘💬✅☑️]\s*",
]


def _is_promo_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    for pat in PROMO_PATTERNS:
        if re.search(pat, s):
            return True
    return False


def strip_tail(text: str) -> str:
    """从末尾剥掉推广/引流行。"""
    lines = text.split("\n")
    while lines and _is_promo_line(lines[-1]):
        lines.pop()
    return "\n".join(lines).strip()


# ---------- 分段：纯文本 -> 结构化 blocks ----------
def article_blocks(text: str) -> list[dict]:
    """把纯文本切成结构化段落。类型：title / h2 / p / list / quote / divider。"""
    lines = text.strip().splitlines()
    blocks: list[dict] = []
    lst: list[str] = []

    def flush() -> None:
        if lst:
            blocks.append({"type": "list", "items": list(lst)})
            lst.clear()

    for raw in lines:
        value = raw.strip()
        if not value:
            flush()
            continue
        bullet = re.match(r"^(?:[-*•]|\d+[.)、])\s+(.+)$", value)
        if bullet:
            lst.append(bullet[1])
            continue
        flush()
        heading = re.match(r"^(#{1,6})\s+(.+)$", value)
        if heading:
            blocks.append({
                "type": "title" if heading[1] == "#" and not any(
                    b["type"] == "title" for b in blocks
                ) else "h2",
                "text": heading[2],
            })
            continue
        if re.match(r"^[-*_]{3,}$", value):
            blocks.append({"type": "divider"})
            continue
        if value.startswith(">"):
            blocks.append({"type": "quote", "text": value.lstrip(">").strip()})
            continue
        blocks.append({
            "type": "title" if (not blocks and len(value) <= 80
                                 and not re.search(r"[。！？]$", value)) else "p",
            "text": value,
        })
    flush()
    return blocks


# ---------- 公众号 HTML 模板 ----------
# 主题配色
THEMES = {
    "tech": {"accent": "#1a6bff", "title": "#1a1a1a", "body": "#333333",
             "quote": "#57606a", "divider": "#1a6bff"},
    "finance": {"accent": "#c0392b", "title": "#1a1a1a", "body": "#333333",
                "quote": "#57606a", "divider": "#c0392b"},
    "simple": {"accent": "#111111", "title": "#111111", "body": "#333333",
               "quote": "#666666", "divider": "#dddddd"},
}


def render_blocks(blocks: list[dict], theme: str = "tech") -> str:
    """把 blocks 渲染成公众号风格 HTML（内联样式）。"""
    t = THEMES.get(theme, THEMES["tech"])
    out: list[str] = []
    for b in blocks:
        typ = b["type"]
        if typ == "title":
            out.append(
                f'<h1 style="font-size:22px;font-weight:700;color:{t["title"]};'
                f'line-height:1.4;margin:0 0 18px;text-align:center;">'
                f'{html.escape(b["text"])}</h1>'
            )
        elif typ == "h2":
            out.append(
                f'<h2 style="font-size:18px;font-weight:700;color:{t["title"]};'
                f'line-height:1.4;margin:26px 0 12px;padding-left:12px;'
                f'border-left:4px solid {t["accent"]};">'
                f'{html.escape(b["text"])}</h2>'
            )
        elif typ == "p":
            out.append(
                f'<p style="font-size:16px;color:{t["body"]};line-height:1.8;'
                f'margin:0 0 16px;text-align:justify;">'
                f'{html.escape(b["text"])}</p>'
            )
        elif typ == "list":
            items = "".join(
                f'<li style="font-size:16px;color:{t["body"]};line-height:1.8;'
                f'margin:6px 0;">{html.escape(i)}</li>'
                for i in b["items"]
            )
            out.append(
                f'<ul style="margin:0 0 16px;padding-left:24px;">{items}</ul>'
            )
        elif typ == "quote":
            out.append(
                f'<blockquote style="font-size:15px;color:{t["quote"]};'
                f'line-height:1.7;margin:0 0 16px;padding:10px 16px;'
                f'background:#f6f8fa;border-left:3px solid {t["divider"]};">'
                f'{html.escape(b["text"])}</blockquote>'
            )
        elif typ == "divider":
            out.append(
                f'<p style="text-align:center;margin:22px 0;">'
                f'<span style="display:inline-block;width:60px;height:2px;'
                f'background:{t["divider"]};border-radius:1px;"></span></p>'
            )
    return "\n".join(out)


def to_wechat_html(text: str, theme: str = "tech") -> str:
    """中文原文 -> 公众号排版 HTML（完整 section 包裹）。"""
    text = strip_tail(text)
    blocks = article_blocks(text)
    body = render_blocks(blocks, theme)
    return (
        '<section style="font-family:-apple-system,BlinkMacSystemFont,'
        '\'Helvetica Neue\',\'PingFang SC\',\'Microsoft YaHei\',sans-serif;'
        'padding:0 2px;max-width:680px;margin:0 auto;">\n'
        f'{body}\n'
        '</section>'
    )


def to_plain_text(text: str) -> str:
    """中文原文 -> 纯文本（用于小红书正文/摘要，去 HTML）。"""
    text = strip_tail(text)
    blocks = article_blocks(text)
    lines: list[str] = []
    for b in blocks:
        if b["type"] == "list":
            lines.extend(f"· {i}" for i in b["items"])
        elif b["type"] == "divider":
            lines.append("")
        else:
            lines.append(b.get("text", ""))
    return "\n".join(lines).strip()


def first_sentence(text: str, limit: int = 40) -> str:
    """取第一句做标题/摘要，超过 limit 截断。"""
    t = text.strip()
    for sep in ("。", "！", "？", "；", "\n"):
        idx = t.find(sep)
        if 0 < idx <= limit:
            return t[:idx + 1]
    return t[:limit] + ("…" if len(t) > limit else "")
