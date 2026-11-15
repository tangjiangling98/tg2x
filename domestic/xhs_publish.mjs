// 小红书笔记发布（移植自 AIMedia electron/xhs.cjs publishXhsNote）
// 用法：node xhs_publish.mjs <payload.json>
// payload.json 字段：cookie, title, desc, images(本地图片路径数组), topics, content_declaration, original
import fs from 'node:fs';
import crypto from 'node:crypto';
import { Client } from 'xhshow-js';

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';

// ---------- 工具 ----------
function cookieToDict(cookieStr) {
  const out = {};
  String(cookieStr || '').split(';').forEach((part) => {
    const idx = part.indexOf('=');
    if (idx <= 0) return;
    const key = part.slice(0, idx).trim();
    const value = part.slice(idx + 1).trim();
    if (key) out[key] = value;
  });
  return out;
}

function sha1(data) { return crypto.createHash('sha1').update(data).digest(); }
function hmacSha1(key, data) { return crypto.createHmac('sha1', key).update(data).digest(); }

function xhsCosAuthorization(method, url, headers = {}) {
  const parsed = new URL(url);
  const start = Math.floor(Date.now() / 1000);
  const keyTime = `${start};${start + 86400}`;
  const params = [...parsed.searchParams.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, value]) => `${encodeURIComponent(key.toLowerCase())}=${encodeURIComponent(value)}`)
    .join('&');
  const signedHeaders = Object.entries(headers)
    .map(([key, value]) => [key.toLowerCase(), String(value)])
    .sort(([a], [b]) => a.localeCompare(b));
  const headerNames = signedHeaders.map(([key]) => key).join(';');
  const headerValues = signedHeaders.map(([key, value]) => `${key}=${encodeURIComponent(value)}`).join('&');
  const httpString = `${method.toLowerCase()}\n${parsed.pathname}\n${params}\n${headerValues}\n`;
  const stringToSign = `sha1\n${keyTime}\n${sha1(httpString).toString('base64')}\n`;
  const signature = hmacSha1(hmacSha1('null', keyTime), stringToSign).toString('base64');
  return `q-sign-algorithm=sha1&q-ak=null&q-sign-time=${keyTime}&q-key-time=${keyTime}&q-header-list=${headerNames}&q-url-param-list=${[...parsed.searchParams.keys()].map((k) => k.toLowerCase()).sort().join(';')}&q-signature=${signature}`;
}

function parsePngSize(buf) {
  if (buf.length < 24 || buf.readUInt32BE(12) !== 0x49484452) return null;
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}
function parseJpegSize(buf) {
  let i = 2;
  while (i + 9 < buf.length) {
    if (buf[i] !== 0xff) { i += 1; continue; }
    const marker = buf[i + 1];
    if (marker >= 0xc0 && marker <= 0xcf && marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc) {
      return { height: buf.readUInt16BE(i + 5), width: buf.readUInt16BE(i + 7) };
    }
    const len = buf.readUInt16BE(i + 2);
    i += 2 + len;
  }
  return null;
}
function imageSize(buf) {
  if (buf.length >= 8 && buf[0] === 0x89 && buf[1] === 0x50) return parsePngSize(buf);
  if (buf.length >= 3 && buf[0] === 0xff && buf[1] === 0xd8) return parseJpegSize(buf);
  return { width: 900, height: 1200 };
}

function fileToImage(path) {
  const buf = fs.readFileSync(path);
  const lower = path.toLowerCase();
  const mime = lower.endsWith('.png') ? 'png' : lower.endsWith('.webp') ? 'webp' : 'jpeg';
  return { buf, mime, dataUrl: `data:image/${mime};base64,${buf.toString('base64')}` };
}

// ---------- 签名请求 ----------
const client = new Client();
async function buildSignedHeaders(method, uri, body, cookieStr, site = 'creator') {
  const cookies = cookieToDict(cookieStr);
  const a1 = cookies.a1 || cookies.A1 || '';
  if (!a1) throw new Error('Cookie 缺少 a1 字段，请重新从已登录的小红书网页复制完整 Cookie');
  const xT = client.getXT();
  return {
    'x-s': client.signXS(method, uri, a1, 'xhs-pc-web', body),
    'x-t': String(xT),
    'x-s-common': client.signXSCommon(cookies),
    'x-b3-traceid': client.getB3TraceId(),
    'x-xray-traceid': client.getXrayTraceId(),
    'user-agent': UA,
    cookie: String(cookieStr || ''),
    'content-type': 'application/json;charset=UTF-8',
    origin: site === 'creator' ? 'https://creator.xiaohongshu.com' : 'https://www.xiaohongshu.com',
    referer: site === 'creator' ? 'https://creator.xiaohongshu.com/' : 'https://www.xiaohongshu.com/',
  };
}

async function xhsFetchJson(label, url, options, cookieStr, site) {
  const uri = new URL(url);
  const method = String(options.method || 'GET').toUpperCase();
  const body = options.body ? JSON.stringify(options.body) : null;
  const headers = await buildSignedHeaders(method, uri.pathname + uri.search, options.body, cookieStr, site);
  const res = await fetch(url, { method, headers, body, signal: AbortSignal.timeout(30000) });
  const text = await res.text().catch(() => '');
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { /* keep null */ }
  if (!res.ok) throw new Error(`${label} 返回 HTTP ${res.status}：${text.slice(0, 300)}`);
  if (!data || data.success !== true) throw new Error(`${label} 失败：${data?.msg || data?.message || text.slice(0, 300)}`);
  return data;
}

async function searchXhsTopic(cookieStr, keyword, desc) {
  try {
    const data = await xhsFetchJson('话题搜索', 'https://edith.xiaohongshu.com/web_api/sns/v1/search/topic', {
      method: 'POST',
      body: { keyword, suggest_topic_request: { title: '', desc: desc || '' }, page: { page_size: 20, page: 1 } },
    }, cookieStr, 'creator');
    const list = data?.data?.topic_info_dtos || [];
    const exact = list.find((t) => String(t.name || '').toLowerCase() === String(keyword).toLowerCase());
    const picked = exact || list.find((t) => t.id && t.name);
    return picked ? { id: String(picked.id), name: String(picked.name), type: 'topic' } : null;
  } catch { return null; }
}

async function recommendXhsTopics(cookieStr, desc, fileIds) {
  const data = await xhsFetchJson('话题推荐', 'https://creator.xiaohongshu.com/api/galaxy/v2/creator/recommend/overt/topics', {
    method: 'POST',
    body: { title: '', desc: desc || '', file_ids: (fileIds || []).join(','), source: 2, topic_round_start_time: Date.now() },
  }, cookieStr, 'creator');
  return (data?.data?.topics || []).filter((t) => t && t.id && t.name);
}

function mapContentDeclaration(value) {
  const map = {
    '虚构演绎，仅供娱乐': 'FICTIONAL_DEDUCTION',
    '笔记含AI合成内容': 'AI_GENERATED_CONTENT',
    '内容包含营销广告': 'MARKETING_AD',
  };
  return map[String(value || '').trim()] || '';
}

async function uploadXhsImages(cookieStr, images) {
  const fileCount = images.length;
  const permit = await xhsFetchJson('图片上传凭证',
    `https://creator.xiaohongshu.com/api/media/v1/upload/creator/permit?biz_name=spectrum&scene=image&file_count=${fileCount}&version=1&source=web`,
    { method: 'GET' }, cookieStr, 'creator');
  const permits = permit?.data?.uploadTempPermits || [];
  const p0 = permits.find((p) => p.uploadAddr && p.fileIds?.length && p.token) || permits[0] || {};
  const host = p0.uploadAddr;
  const fileIds = p0.fileIds || [];
  const token = p0.token || '';
  if (!host || !fileIds.length || !token) throw new Error('小红书图片上传凭证不完整');

  const uploaded = [];
  for (let i = 0; i < images.length; i += 1) {
    const { buf, mime } = images[i];
    const fileId = fileIds[i];
    if (!fileId) throw new Error('图片上传凭证数量不足');
    const size = imageSize(buf);
    const baseUrl = `https://${host}/${fileId}`;
    const signHeaders = { 'content-length': buf.length, host };
    const res = await fetch(baseUrl, {
      method: 'PUT',
      headers: {
        'user-agent': UA,
        'content-type': `image/${mime}`,
        'x-cos-security-token': token,
        authorization: xhsCosAuthorization('PUT', baseUrl, signHeaders),
        origin: 'https://creator.xiaohongshu.com',
      },
      body: buf,
      signal: AbortSignal.timeout(60000),
    });
    if (!res.ok) {
      const t = await res.text().catch(() => '');
      throw new Error(`图片上传失败 HTTP ${res.status}：${t.slice(0, 200)}`);
    }
    uploaded.push({ file_id: fileId, width: size.width, height: size.height, mime: `image/${mime}` });
  }
  return uploaded;
}

async function publishXhsNote({ cookie, title, desc, images, topics = [], original = false, contentDeclaration = '' }) {
  if (!cookie || !String(cookie).trim()) throw new Error('小红书 Cookie 缺失');
  if (!Array.isArray(images) || !images.length) throw new Error('小红书笔记发布需要至少 1 张图片');
  const uploaded = await uploadXhsImages(cookie, images);
  const hashTag = [];
  const recommended = await recommendXhsTopics(cookie, desc, uploaded.map((u) => u.file_id)).catch(() => []);
  const wants = topics.map((tag) => String(tag).replace(/^#/, '').trim()).filter(Boolean);
  for (const t of wants) {
    const hit = recommended.find((r) => String(r.name).trim() === t)
      || recommended.find((r) => String(r.name).includes(t) || t.includes(String(r.name)));
    if (hit) hashTag.push({ id: String(hit.id), name: String(hit.name), type: 'topic' });
    else { const found = await searchXhsTopic(cookie, t, desc); if (found) hashTag.push(found); }
  }
  let finalDesc = String(desc || '');
  finalDesc = finalDesc.replace(/#([^\s#]+)/g, (all, name) => {
    const hit = hashTag.find((h) => h.name === name || h.name.includes(name) || name.includes(h.name));
    return hit ? `#${hit.name}[话题]#` : all;
  });
  const creatorId = (String(cookie).match(/x-user-id-creator\.xiaohongshu\.com=([^;\s]+)/) || [])[1] || '';
  const isOriginal = original === true || original === 'original';
  const optionRelationList = [];
  if (isOriginal && creatorId) {
    optionRelationList.push({ type: 'ORIGINAL_STATEMENT', relationList: [{ bizType: 'ORIGINAL_STATEMENT', bizId: creatorId, extraInfo: '{}' }] });
  }
  const contentCode = mapContentDeclaration(contentDeclaration);
  if (contentCode) optionRelationList.push({ type: contentCode, relationList: [] });
  const body = {
    common: {
      type: 'normal', note_id: '',
      source: JSON.stringify({ type: 'web', ids: '', extraInfo: JSON.stringify({ systemId: 'web' }) }),
      title: String(title || '').slice(0, 20), desc: finalDesc, ats: [], hash_tag: hashTag,
      business_binds: JSON.stringify({
        version: 1, noteId: 0, bizType: 0, noteOrderBind: {}, notePostTiming: {},
        noteCollectionBind: { id: '' }, noteSketchCollectionBind: { id: '' },
        userDeclarationBind: { origin: isOriginal ? 1 : 2 }, coProduceBind: { enable: isOriginal },
        noteCopyBind: { copyable: isOriginal }, interactionPermissionBind: { commentPermission: 0 },
        optionRelationList,
      }),
      privacy_info: { op_type: 1, type: 0, user_ids: [] }, goods_info: {}, biz_relations: [],
      capa_trace_info: { contextJson: JSON.stringify({
        recommend_title: { recommend_title_id: '', is_use: 3, used_index: -1 },
        recommendTitle: [],
        recommend_topics: { used: hashTag.map((t) => ({ id: t.id, name: t.name, topic_source: 'recommend_exposed_display' })) },
      }) },
    },
    image_info: { images: uploaded.map((u) => ({
      file_id: u.file_id, width: u.width, height: u.height,
      metadata: { source: -1 }, stickers: { version: 2, floating: [] },
      extra_info_json: JSON.stringify({ mimeType: u.mime, image_metadata: { bg_color: '', origin_size: u.width * u.height * 4 } }),
    })) },
    video_info: null,
  };
  const data = await xhsFetchJson('笔记发布', 'https://edith.xiaohongshu.com/web_api/sns/v2/note', { method: 'POST', body }, cookie, 'creator');
  const noteId = String(data?.data?.id || '').trim();
  if (!noteId) throw new Error('小红书发布未返回笔记 ID');
  return { noteId, shareLink: data.share_link || `https://www.xiaohongshu.com/explore/${noteId}` };
}

// ---------- 入口 ----------
const payloadPath = process.argv[2];
if (!payloadPath) { console.error('用法：node xhs_publish.mjs <payload.json>'); process.exit(2); }
const payload = JSON.parse(fs.readFileSync(payloadPath, 'utf-8'));
try {
  const images = (payload.images || []).map((p) => fileToImage(p));
  const result = await publishXhsNote({
    cookie: payload.cookie,
    title: payload.title || '',
    desc: payload.desc || '',
    images,
    topics: payload.topics || [],
    original: payload.original || false,
    contentDeclaration: payload.content_declaration || '',
  });
  console.log(JSON.stringify({ success: true, ...result }));
} catch (err) {
  console.log(JSON.stringify({ success: false, error: err.message || String(err) }));
  process.exit(1);
}
