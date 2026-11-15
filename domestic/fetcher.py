"""抓取 TG 频道的中文原文（自包含，不依赖 tg2x 包）。

复用 tg2x 的「网页预览页 t.me/s/<channel>」思路：零凭证、不会封号。
只取中文原文，不做翻译。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

URL_RE = re.compile(r"url\(['\"]?(.*?)['\"]?\)")


@dataclass
class CnPost:
    """一条中文原帖。"""
    channel: str
    message_id: int
    text: str = ""
    posted_at: str = ""
    url: str = ""
    media_urls: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.channel}:{self.message_id}"


def fetch_channel(channel: str, limit: int = 10, timeout: int = 25) -> list[CnPost]:
    """抓取公开频道最新 limit 条（按 message_id 升序返回）。"""
    channel = channel.lstrip("@")
    url = f"https://t.me/s/{channel}"
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": UA,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    resp = sess.get(url, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"抓取失败 HTTP {resp.status_code}：{url}")

    soup = BeautifulSoup(resp.text, "lxml")
    out: list[CnPost] = []
    for wrap in soup.select("div.tgme_widget_message"):
        data_post = wrap.get("data-post") or ""
        if "/" not in data_post:
            continue
        ch, _, mid = data_post.partition("/")
        try:
            message_id = int(mid)
        except ValueError:
            continue

        text_el = wrap.select_one(".tgme_widget_message_text")
        text = ""
        if text_el is not None:
            for br in text_el.find_all("br"):
                br.replace_with("\n")
            text = text_el.get_text("", strip=False).strip()

        time_el = wrap.select_one("time[datetime]")
        posted_at = time_el["datetime"] if time_el else ""

        media: list[str] = []
        for el in wrap.select(".tgme_widget_message_photo_wrap"):
            m = URL_RE.search(el.get("style") or "")
            if m:
                media.append(m.group(1))

        out.append(CnPost(
            channel=ch,
            message_id=message_id,
            text=text,
            posted_at=posted_at,
            url=f"https://t.me/{ch}/{message_id}",
            media_urls=media,
        ))

    out.sort(key=lambda p: p.message_id)
    return out[-limit:]
