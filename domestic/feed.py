"""从 GitHub 仓库拉取 tg2x 导出的中文原文（data/cn_feed.json）。

为什么走这里而不是本机直接抓 t.me：国内网络访问不了 t.me，
而 tg2x 的 GitHub Actions（海外）能抓，抓完把中文原文落盘到仓库。
"""
from __future__ import annotations

import base64
import json

import requests

from fetcher import CnPost


def fetch_cn_feed(repo: str = "tangjun937/tg2x",
                  path: str = "data/cn_feed.json",
                  timeout: int = 30) -> list[CnPost]:
    """拉取最新中文原文队列，返回按 message_id 升序的 CnPost 列表。"""
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    sess = requests.Session()
    sess.trust_env = False  # 绕过本机代理直连
    sess.headers.update({"Accept": "application/vnd.github+json"})
    r = sess.get(url, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"拉取 cn_feed.json 失败 HTTP {r.status_code}")
    raw = base64.b64decode(r.json()["content"]).decode("utf-8")
    feed = json.loads(raw)
    channel = feed.get("channel", "").lstrip("@")
    out: list[CnPost] = []
    for p in feed.get("posts", []):
        text = (p.get("text") or "").strip()
        if not text:
            continue
        out.append(CnPost(
            channel=channel,
            message_id=int(p.get("message_id", 0)),
            text=text,
            posted_at=p.get("posted_at", "") or "",
            url=p.get("url", "") or "",
        ))
    out.sort(key=lambda x: x.message_id)
    return out
