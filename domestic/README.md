# XjianglinX 国内平台分发

把 @YMISH3333 频道的**中文原文**排版后，同步发布到**公众号草稿箱**和**小红书**。

## 架构（重要，先看懂再操作）

| 环节 | 跑在哪 | 为什么 |
|---|---|---|
| 抓取 @YMISH3333 + 翻译英文发 X | GitHub Actions（云端） | 国内访问不了 t.me，海外才能抓 |
| 中文原文导出 | GitHub Actions 落盘到仓库 `data/cn_feed.json` | 中转给本机 |
| 排版 + 配图 + 发公众号/小红书 | **你的电脑（本机常驻）** | 国内平台风控严，必须用你的 IP 和登录态 |

所以：X 账号照常全自动（本机可关机）；国内平台需要**本机开机 + 运行 `start_daemon.bat`**。

---

## 第 1 步：获取公众号 Cookie（只推草稿箱，不群发）

1. 电脑浏览器打开 https://mp.weixin.qq.com ，用公众号管理员微信**扫码登录**；
2. 登录成功后按 **F12** 打开开发者工具，切到 **Console（控制台）**；
3. 输入下面这行，回车：
   ```
   document.cookie
   ```
4. 把输出的一整串（`xxx=1; yyy=2; ...`）**全部复制**下来。

> 这串里必须包含 `slave_user`、`slave_sid`、`master_sid` 之类的字段，否则保存草稿会失败。
> 如果 `document.cookie` 很短/没这些字段，改用 Network（网络）标签：刷新页面，点任一 `mp.weixin.qq.com` 的请求，在 **Request Headers** 里复制 `Cookie` 一整行。

## 第 2 步：获取小红书 Cookie（真实发布，强制配图）

1. 电脑浏览器打开 https://creator.xiaohongshu.com ，**扫码登录**（创作者中心）；
2. F12 → **Console** → 输入 `document.cookie` 回车；
3. 复制输出的一整串。

> 这串里必须包含 `a1=` 字段，签名依赖它。若 `document.cookie` 拿不到 `a1`，改用 Network 标签复制完整 `Cookie` 请求头。

## 第 3 步：填写配置

编辑同目录的 `config.yaml`：

```yaml
wechat:
  enabled: true          # 改成 true
  cookie: "第1步复制的公众号cookie"

xhs:
  enabled: true          # 改成 true（不想发小红书就保持 false）
  cookie: "第2步复制的小红书cookie"
```

## 第 4 步：运行

- **手动跑一次测试**：双击 `run_once.bat`
- **常驻运行**（每 30 分钟一轮）：双击 `start_daemon.bat`

首次运行会先建立基线（不搬运历史），之后每轮只发最新 1 条。

---

## 注意事项

1. **公众号只能推草稿箱**：个人订阅号无法通过接口群发，脚本保存到草稿箱后，需要你在手机「订阅号助手」或公众号后台点一下「发布」。
2. **Cookie 会过期**：公众号约 7 天、小红书可能更短。失效后重新走第 1/2 步复制新的填进 `config.yaml` 即可。
3. **小红书风控**：海外 IP / 异地登录易触发验证码甚至封号，所以必须本机跑；建议不要频繁改 Cookie、不要一天发太多。
4. **AI 内容标注**：小红书要求 AI 合成内容主动标注，配置里已默认 `笔记含AI合成内容`，不要关掉。
5. **去重独立**：国内分发有自己的 `state.json`，和 X 账号的英文链路互不影响。

## 文件说明

| 文件 | 作用 |
|---|---|
| `daemon.py` | 主流程：拉取 → 排版 → 配图 → 公众号/小红书 → 去重 |
| `feed.py` | 从 GitHub 拉 tg2x 导出的中文原文 |
| `layout.py` | 排版（纯文本 → 公众号风格 HTML） |
| `cover.py` | 配图（竖版卡片图，公众号封面 + 小红书配图共用） |
| `wechat_draft.py` | 公众号草稿箱发布 |
| `xhs_publish.mjs` | 小红书发布（Node + xhshow-js 签名） |
| `config.yaml` | 配置（频道、Cookie、平台开关） |
| `state.json` | 去重状态（自动生成，勿手改） |
