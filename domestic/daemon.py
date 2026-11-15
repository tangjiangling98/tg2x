"""国内平台分发主流程（本机常驻运行）。

每 interval_minutes 轮询一次 @YMISH3333 频道，把最新中文原文：
  排版 -> 配图 -> 公众号草稿箱(可选) -> 小红书(可选)
与 X 账号的英文链路完全独立，互不影响。

用法：
  python daemon.py            # 常驻循环
  python daemon.py --once     # 只跑一轮后退出（测试用）
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

import yaml

from cover import render_cover
from feed import fetch_cn_feed
from layout import first_sentence, strip_tail, to_plain_text, to_wechat_html
from wechat_draft import create_draft

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.yaml")
STATE_PATH = os.path.join(HERE, "state.json")
OUT_DIR = os.path.join(HERE, "out")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_msgid": 0}


def save_state(state: dict) -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def log(msg: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def run_once(cfg: dict) -> dict:
    channel = cfg.get("channel", "").lstrip("@")
    max_per = int(cfg.get("max_per_cycle", 1) or 1)
    theme = (cfg.get("cover", {}) or {}).get("theme", "tech")
    feed_cfg = cfg.get("feed", {}) or {}

    try:
        posts = fetch_cn_feed(
            repo=feed_cfg.get("repo", "tangjun937/tg2x"),
            path=feed_cfg.get("path", "data/cn_feed.json"),
        )
    except Exception as e:
        log(f"拉取中文原文失败：{e}")
        return {"fetched": 0, "new": 0, "error": str(e)}

    if not posts:
        return {"fetched": 0, "new": 0}

    state = load_state()
    last = int(state.get("last_msgid", 0) or 0)
    if last == 0:
        # 首次运行：建立基线，不搬运历史
        state["last_msgid"] = posts[-1].message_id
        save_state(state)
        log(f"首次运行：已为 {channel} 建立基线（最新 {posts[-1].message_id}），本轮不发布")
        return {"fetched": len(posts), "new": 0, "baseline": True}

    fresh = [p for p in posts if p.message_id > last]
    if not fresh:
        return {"fetched": len(posts), "new": 0}

    fresh = fresh[-max_per:]
    result = {"fetched": len(posts), "new": len(fresh), "published": 0, "failed": 0}
    os.makedirs(OUT_DIR, exist_ok=True)

    for p in fresh:
        log(f"处理新帖 [{p.key}] 共 {len(p.text)} 字")
        text = p.text.strip()
        if not text:
            log(f"  [{p.key}] 空文本，跳过")
            state["last_msgid"] = p.message_id
            continue

        text = strip_tail(text)
        title = first_sentence(text, limit=40)
        plain = to_plain_text(text)
        html_body = to_wechat_html(text, theme)

        # 配图
        cover_path = os.path.join(OUT_DIR, f"cover_{p.message_id}.png")
        cover_cfg = cfg.get("cover", {}) or {}
        try:
            render_cover(title, plain, cover_path,
                         width=int(cover_cfg.get("width", 1080)),
                         height=int(cover_cfg.get("height", 1440)),
                         theme=theme,
                         font_path=cover_cfg.get("font_path", "") or "",
                         source=cover_cfg.get("source", "") or "")
            log(f"  [{p.key}] 配图已生成：{cover_path}")
        except Exception as e:
            cover_path = ""
            log(f"  [{p.key}] 配图生成失败（忽略）：{e}")

        ok = True

        # 公众号草稿箱
        wc = cfg.get("wechat", {}) or {}
        if wc.get("enabled"):
            r = create_draft(
                wc.get("cookie", ""),
                title=title,
                content=html_body,
                author=wc.get("author", "") or "",
                digest=first_sentence(text, limit=80),
                cover_path=cover_path,
                fingerprint=wc.get("fingerprint", "") or "35dc47301bd07b69891ae7968e00661d",
            )
            if r.get("success"):
                log(f"  [{p.key}] 公众号草稿已保存 appmsgid={r.get('appmsgid')}")
            else:
                ok = False
                log(f"  [{p.key}] 公众号保存失败：{r.get('error')} {r.get('detail', '')}")

        # 小红书
        xhs = cfg.get("xhs", {}) or {}
        if xhs.get("enabled"):
            payload = {
                "cookie": xhs.get("cookie", ""),
                "title": (xhs.get("title") or title or "")[:20],
                "desc": plain,
                "images": [cover_path] if cover_path else [],
                "topics": xhs.get("topics", []) or [],
                "original": False,
                "content_declaration": xhs.get("content_declaration", "") or "",
            }
            payload_path = os.path.join(OUT_DIR, f"_xhs_{p.message_id}.json")
            with open(payload_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            try:
                out = subprocess.run(
                    ["node", os.path.join(HERE, "xhs_publish.mjs"), payload_path],
                    capture_output=True, text=True, timeout=120, cwd=HERE,
                )
                resp = json.loads(out.stdout.strip().splitlines()[-1]) if out.stdout.strip() else {}
                if resp.get("success"):
                    log(f"  [{p.key}] 小红书已发布 noteId={resp.get('noteId')}")
                else:
                    ok = False
                    log(f"  [{p.key}] 小红书发布失败：{resp.get('error')}")
            except Exception as e:
                ok = False
                log(f"  [{p.key}] 小红书调用异常：{e}")

        result["published" if ok else "failed"] += 1
        state["last_msgid"] = p.message_id

    save_state(state)
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="只跑一轮后退出")
    args = ap.parse_args()

    if not os.path.exists(CONFIG_PATH):
        print("缺少 config.yaml，请先按 README 配置")
        sys.exit(1)

    cfg = load_config()
    interval = int(cfg.get("interval_minutes", 30) or 30)
    log(f"国内分发启动：频道 @{cfg.get('channel','')}，间隔 {interval} 分钟")

    if args.once:
        r = run_once(cfg)
        log(f"本轮结果：{json.dumps(r, ensure_ascii=False)}")
        return

    while True:
        try:
            r = run_once(cfg)
            log(f"本轮结果：{json.dumps(r, ensure_ascii=False)}")
        except Exception as e:
            log(f"本轮异常：{e}")
        log(f"休眠 {interval} 分钟…")
        time.sleep(interval * 60)


if __name__ == "__main__":
    main()
