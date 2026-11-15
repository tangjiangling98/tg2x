"""公众号草稿箱发布（只推草稿箱，不群发）。

移植自 AIMedia electron/wechatMp.cjs 的 createDraft：模拟 mp.weixin.qq.com
后台网页版，用登录 Cookie + token 调 operate_appmsg 保存草稿。
"""
from __future__ import annotations

import json
import random
import re
import uuid

import requests

BASE_URL = "https://mp.weixin.qq.com"
DEFAULT_FINGERPRINT = "35dc47301bd07b69891ae7968e00661d"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def _dedupe_cookies(cookie: str) -> str:
    """同名 cookie 只保留最后一个，避免重复 key 导致 invalid csrf。"""
    m: dict[str, str] = {}
    for part in cookie.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            k, v = k.strip(), v.strip()
            if k:
                m[k] = v
    return "; ".join(f"{k}={v}" for k, v in m.items())


def _new_session(cookie: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Cookie": _dedupe_cookies(cookie),
        "Referer": BASE_URL + "/",
        "Origin": BASE_URL,
        "X-Requested-With": "XMLHttpRequest",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    return s


def extract_token(session: requests.Session) -> str:
    """从首页提取最新 token（登录态下的后台 token）。"""
    r = session.get(BASE_URL + "/", allow_redirects=True, timeout=30)
    token = ""
    m = re.search(r"token=(\d{6,})", r.url)
    if m:
        token = m.group(1)
    if not token:
        for pat in (
            r'window\.wx\.commonData\s*=\s*\{[^}]*?token\s*[:=]\s*["\']?(\d{6,})',
            r"\btoken\s*[:=]\s*[" + '"' + r"']?(\d{6,})",
            r"[&?]token=(\d{6,})",
        ):
            m = re.search(pat, r.text)
            if m:
                token = m.group(1)
                break
    if not token:
        raise RuntimeError("未能从公众号后台提取 token，Cookie 可能已失效，请重新复制")
    return token


def _build_req_field() -> str:
    """operate_appmsg 的 req 字段（固定结构）。"""
    return json.dumps({
        "idx_infos": [{
            "save_old": 0,
            "cps_info": {"cps_import": 0},
            "red_packet_cover_list": {},
            "podcast_task_info": None,
            "claim_source": {},
            "line_info": {"is_appmsg_flag": 0, "scene": 2},
            "window_product": {},
            "link_info": {},
            "appmsg_link": {},
            "weapp_link": {},
            "yqj_info": {},
            "ai_pic_info": {"cover_source": 0, "ai_pic_id": [], "cover_pic_id": ""},
            "single_video_snap_card": {},
            "product_activity": {},
            "footer_gift_activity": {},
            "footer_common_shops": [],
            "location": {},
        }],
        "appmsg_id": 0,
        "is_use_flag": 0,
        "template_version": "06082702",
    }, ensure_ascii=False)


def _build_draft_fields(token: str, fingerprint: str, *, title: str, author: str,
                        digest: str, content: str, cover: str) -> list[tuple[str, str]]:
    """构造保存草稿的 multipart 字段（对齐真实编辑器抓包）。"""
    cover235 = cover169 = cover34 = cover11 = cover
    crop_list = ""
    show_cover_pic = 1 if cover else 0
    fields = [
        ("token", token), ("lang", "zh_CN"), ("f", "json"), ("ajax", "1"),
        ("fingerprint", fingerprint), ("random", str(random.random())),
        ("AppMsgId", ""), ("count", "1"), ("data_seq", "0"),
        ("operate_from", "Chrome"), ("isnew", "0"), ("articlenum", "1"),
        ("pre_timesend_set", "0"), ("is_finder_video0", "0"),
        ("finder_draft_id0", "0"), ("applyori0", "0"),
        ("ad_video_transition0", ""), ("can_reward0", "0"),
        ("pay_gifts_count0", "0"), ("reward_reply_id0", ""),
        ("related_video0", ""), ("is_video_recommend0", "0"),
        ("title0", title), ("is_user_title0", ""), ("author0", author),
        ("writerid0", "0"), ("fileid0", "0"), ("digest0", digest),
        ("auto_gen_digest0", "0"), ("content0", content), ("sourceurl0", ""),
        ("last_choose_cover_from0", "0"), ("need_open_comment0", "0"),
        ("only_fans_can_comment0", "0"), ("only_fans_days_can_comment0", "0"),
        ("reply_flag0", "2"), ("not_pay_can_comment0", "0"),
        ("auto_elect_comment0", "1"), ("auto_elect_reply0", "1"),
        ("option_version0", "5"), ("open_fansmsg0", "0"),
        ("cdn_url0", cover), ("cdn_235_1_url0", cover235),
        ("cdn_16_9_url0", cover169), ("cdn_3_4_url0", cover34),
        ("cdn_1_1_url0", cover11), ("cdn_finder_url0", ""), ("cdn_video_url0", ""),
        ("cdn_url_back0", ""), ("crop_list0", crop_list), ("app_cover_auto0", "0"),
        ("music_id0", ""), ("video_id0", ""), ("voteid0", ""), ("voteismlt0", ""),
        ("supervoteid0", ""), ("super_vote_id0", ""), ("vid_type0", ""),
        ("show_cover_pic0", str(show_cover_pic)), ("copyright_type0", "0"),
        ("is_cartoon_copyright0", "0"),
        ("copyright_img_list0", '{"max_width":586,"img_list":[]}'),
        ("releasefirst0", ""), ("platform0", ""), ("reprint_permit_type0", ""),
        ("allow_fast_reprint0", "1"), ("allow_reprint0", "0"),
        ("allow_reprint_modify0", "0"), ("original_article_type0", ""),
        ("ori_white_list0", '{"white_list":[]}'), ("video_ori_status0", ""),
        ("hit_nickname0", ""), ("free_content0", ""), ("fee0", "0"),
        ("ad_id0", ""), ("guide_words0", ""), ("is_share_copyright0", "0"),
        ("share_copyright_url0", ""), ("source_article_type0", ""),
        ("reprint_recommend_title0", ""), ("reprint_recommend_content0", ""),
        ("share_page_type0", "0"), ("share_imageinfo0", '{"list":[]}'),
        ("share_video_id0", ""), ("dot0", "{}"), ("share_voice_id0", ""),
        ("share_finder_audio_username0", ""), ("share_finder_audio_exportid0", ""),
        ("mmlistenitem_json_buf0", ""), ("insert_ad_mode0", "2"),
        ("categories_list0", "[]"), ("compose_info0", '{"list":""}'),
        ("is_pay_subscribe0", "0"), ("pay_fee0", ""),
        ("pay_preview_percent0", ""), ("pay_desc0", ""), ("pay_album_info0", ""),
        ("appmsg_album_info0", '{"appmsg_album_infos":[]}'),
        ("can_insert_ad0", "1"), ("open_keyword_ad0", "1"), ("open_comment_ad0", "1"),
        ("audio_info0", '{"audio_infos":[]}'), ("danmu_pub_type0", "0"),
        ("mp_video_info0", '{"list":[]}'), ("appmsg_danmu_pub_type0", ""),
        ("is_set_sync_to_finder0", "0"), ("sync_to_finder_cover0", ""),
        ("sync_to_finder_cover_source0", ""), ("import_to_finder0", "0"),
        ("import_from_finder_export_id0", ""), ("style_type0", "0"),
        ("sticker_info0", '{"is_stickers":0,"common_stickers_num":0,'
         '"union_stickers_num":0,"sticker_id_list":[],"has_invalid_sticker":0}'),
        ("new_pic_process0", "0"), ("disable_recommend0", "0"),
        ("claim_source_type0", "0"), ("is_user_no_claim_source0", "0"),
        ("msg_index_id0", ""), ("convert_to_image_share_page0", ""),
        ("convert_from_image_share_page0", ""), ("incontent_ad_count0", "2"),
        ("multi_picture_cover0", "0"), ("title_gen_type0", "0"),
        ("req", _build_req_field()), ("remind_flag", "null"),
        ("is_auto_type_setting", "3"), ("save_type", "0"), ("isneedsave", "0"),
    ]
    return fields


def _build_multipart(fields: list[tuple[str, str]]) -> tuple[bytes, str]:
    boundary = "----WebKitFormBoundary" + uuid.uuid4().hex[:16]
    crlf = "\r\n"
    parts: list[bytes] = []
    for name, value in fields:
        parts.append(
            f"--{boundary}{crlf}"
            f'Content-Disposition: form-data; name="{name}"{crlf}'
            f"{crlf}{value}{crlf}".encode("utf-8")
        )
    parts.append(f"--{boundary}--{crlf}".encode("utf-8"))
    return b"".join(parts), boundary


def _upload_cover(session: requests.Session, token: str, cover_path: str) -> str:
    """上传封面图到微信 CDN，返回 mmbiz 地址。"""
    with open(cover_path, "rb") as f:
        buf = f.read()
    now = random.randint(10**15, 10**16 - 1)
    boundary = "----WebKitFormBoundary" + uuid.uuid4().hex[:16]
    crlf = "\r\n"
    head = (
        f"--{boundary}{crlf}"
        f'Content-Disposition: form-data; name="id"{crlf}{crlf}w{now}{crlf}'
        f"--{boundary}{crlf}"
        f'Content-Disposition: form-data; name="name"{crlf}{crlf}cover.png{crlf}'
        f"--{boundary}{crlf}"
        f'Content-Disposition: form-data; name="type"{crlf}{crlf}image/png{crlf}'
        f"--{boundary}{crlf}"
        f'Content-Disposition: form-data; name="lastModifiedDate"{crlf}{crlf}'
        f"Thu Nov 13 2026 20:00:00 GMT+0800 (China Standard Time){crlf}"
        f"--{boundary}{crlf}"
        f'Content-Disposition: form-data; name="size"{crlf}{crlf}{len(buf)}{crlf}'
        f"--{boundary}{crlf}"
        f'Content-Disposition: form-data; name="upfile"; filename="cover.png"{crlf}'
        f"Content-Type: image/png{crlf}{crlf}"
    ).encode("utf-8")
    tail = f"{crlf}--{boundary}--{crlf}".encode("utf-8")
    body = head + buf + tail
    url = (f"{BASE_URL}/cgi-bin/uploadimg2cdn?lang=zh_CN&token={token}"
           f"&t={random.random()}")
    r = session.post(url, data=body, headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }, timeout=90)
    try:
        data = r.json()
    except Exception:
        data = {}
    url_value = (data.get("url") or data.get("cdn_url")
                 or (data.get("data") or {}).get("url") or "")
    if data.get("base_resp", {}).get("ret") != 0 or not url_value:
        raise RuntimeError("封面上传失败：" + json.dumps(data, ensure_ascii=False)[:300])
    return url_value


def create_draft(cookie: str, *, title: str, content: str, author: str = "",
                 digest: str = "", cover_path: str = "",
                 fingerprint: str = DEFAULT_FINGERPRINT) -> dict:
    """保存一篇草稿到公众号草稿箱。返回 {success, appmsgid} 或 {success:false, error}。"""
    if not cookie.strip():
        return {"success": False, "error": "公众号 Cookie 为空"}
    session = _new_session(cookie)
    try:
        token = extract_token(session)
    except RuntimeError as e:
        return {"success": False, "error": str(e)}

    # 预热编辑器页面，建立会话上下文
    try:
        session.get(
            f"{BASE_URL}/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1"
            f"&type=77&createType=0&token={token}&lang=zh_CN", timeout=30)
    except Exception:
        pass

    cover = ""
    if cover_path:
        try:
            cover = _upload_cover(session, token, cover_path)
        except Exception as e:
            # 封面上传失败不阻断，降级为无封面
            print(f"[wechat] 封面上传失败，降级为无封面：{e}")

    fields = _build_draft_fields(token, fingerprint, title=title, author=author,
                                 digest=digest, content=content, cover=cover)
    body, boundary = _build_multipart(fields)
    url = (f"{BASE_URL}/cgi-bin/operate_appmsg?t=ajax-response&sub=create"
           f"&type=77&token={token}&lang=zh_CN")
    r = session.post(url, data=body, headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Referer": f"{BASE_URL}/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit"
                   f"&isNew=1&type=77&createType=0&token={token}&lang=zh_CN",
    }, timeout=60)
    try:
        data = r.json()
    except Exception:
        data = {}
    if data.get("base_resp", {}).get("ret") == 0 or data.get("ret") == "0":
        appmsgid = str(data.get("appMsgId") or data.get("appmsgid")
                       or data.get("appmsg_id") or "")
        return {"success": True, "appmsgid": appmsgid}
    err = (data.get("base_resp", {}).get("err_msg")
           or data.get("msg") or "保存草稿失败")
    return {"success": False, "error": err, "detail": json.dumps(data, ensure_ascii=False)[:300]}
