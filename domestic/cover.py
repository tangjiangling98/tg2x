"""配图生成：把中文快讯渲染成竖版卡片图（公众号封面 + 小红书配图）。

用 Pillow + Windows 自带中文字体，无网络依赖。
"""
from __future__ import annotations

import os
import textwrap

from PIL import Image, ImageDraw, ImageFont

# 主题配色
THEMES = {
    "tech": {"bg": (10, 20, 40), "accent": (26, 107, 255), "text": (240, 244, 248),
             "sub": (160, 175, 190), "tag_bg": (26, 107, 255)},
    "finance": {"bg": (30, 12, 10), "accent": (192, 57, 43), "text": (248, 244, 240),
                "sub": (190, 175, 170), "tag_bg": (192, 57, 43)},
    "simple": {"bg": (250, 250, 250), "accent": (20, 20, 20), "text": (30, 30, 30),
               "sub": (120, 120, 120), "tag_bg": (20, 20, 20)},
}

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",   # 微软雅黑 粗
    r"C:\Windows\Fonts\msyh.ttc",     # 微软雅黑
    r"C:\Windows\Fonts\simhei.ttf",   # 黑体
    r"C:\Windows\Fonts\simsun.ttc",   # 宋体
]


def _find_font(bold: bool = True) -> str:
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    # 兜底：随便找一个 ttc/ttf
    fonts_dir = r"C:\Windows\Fonts"
    if os.path.isdir(fonts_dir):
        for name in os.listdir(fonts_dir):
            if name.lower().endswith((".ttc", ".ttf")):
                return os.path.join(fonts_dir, name)
    raise RuntimeError("未找到可用中文字体")


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _wrap_by_width(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """按像素宽度把文本折成多行。"""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        cur = ""
        for ch in paragraph:
            if font.getlength(cur + ch) <= max_width:
                cur += ch
            else:
                if cur:
                    lines.append(cur)
                cur = ch
        if cur:
            lines.append(cur)
    return lines


def render_cover(title: str, body: str, out_path: str, width: int = 1080,
                 height: int = 1440, theme: str = "tech", font_path: str = "",
                 source: str = "") -> str:
    """生成竖版卡片图，返回保存路径。source 为底部来源标注（留空则不显示）。"""
    t = THEMES.get(theme, THEMES["tech"])
    font_path = font_path or _find_font()

    img = Image.new("RGB", (width, height), t["bg"])
    draw = ImageDraw.Draw(img)

    margin = int(width * 0.09)  # ~97px
    pad = int(width * 0.06)

    # 顶部品牌条
    tag_font = _load_font(font_path, int(width * 0.045))
    tag_text = "全球大事件曝光"
    tag_w = tag_font.getlength(tag_text)
    tag_h = int(width * 0.075)
    draw.rounded_rectangle(
        [margin, int(height * 0.07), margin + tag_w + pad * 2, int(height * 0.07) + tag_h],
        radius=tag_h // 2, fill=t["tag_bg"],
    )
    draw.text((margin + pad, int(height * 0.07) + tag_h // 4),
              tag_text, font=tag_font, fill=(255, 255, 255))

    # 标题（大字）
    title_font = _load_font(font_path, int(width * 0.072))
    title_lines = _wrap_by_width(title, title_font, width - margin * 2)[:6]
    y = int(height * 0.17)
    line_h = int(width * 0.10)
    for ln in title_lines:
        draw.text((margin, y), ln, font=title_font, fill=t["text"])
        y += line_h

    # 分割线
    y += int(width * 0.02)
    draw.rectangle([margin, y, margin + int(width * 0.18), y + int(width * 0.012)],
                   fill=t["accent"])
    y += int(width * 0.06)

    # 正文摘要
    body_font = _load_font(font_path, int(width * 0.04))
    body_lines = _wrap_by_width(body, body_font, width - margin * 2)
    max_lines = (height - y - int(height * 0.14)) // int(width * 0.058)
    if len(body_lines) > max_lines:
        body_lines = body_lines[:max_lines]
        last = body_lines[-1]
        while last and body_font.getlength(last + "…") > width - margin * 2:
            last = last[:-1]
        body_lines[-1] = last + "…"
    for ln in body_lines:
        draw.text((margin, y), ln, font=body_font, fill=t["sub"])
        y += int(width * 0.058)

    # 底部来源（可选）
    if source:
        src_font = _load_font(font_path, int(width * 0.032))
        draw.text((margin, height - int(height * 0.06)), source, font=src_font, fill=t["sub"])

    img.save(out_path, quality=92)
    return out_path
