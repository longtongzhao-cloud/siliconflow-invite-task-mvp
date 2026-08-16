# SiliconFlow 官方网页客户端只读技术验证

验证时间：2026-08-14（Asia/Shanghai）  
角色：上游官方客户端分析工程师  
范围：只分析 SiliconFlow 官方域名的公开页面、响应头、官方文档和无需登录即可下载的前端静态资源。仅执行 GET/HEAD；未发送短信、未登录、未提交验证码、未使用真实账户、未调用任何会改变状态的接口。

## 结论先行

| 能力 | 只读验证结论 | 独立复刻判定 |
|---|---|---|
| 手机短信注册/登录 | 官方前端公开了同源内部接口、请求体形状和两层网易易盾校验；这是网页私有登录流程，不是开放 API | **技术协议可见，但第三方后端代理登录 No-Go**，除非取得 SiliconFlow 明确授权 |
| 用邀请码注册 | 登录页支持 `invitation` 查询参数，提交字段为 `shareCode`，最长 8 位；邀请短链为 `/i/{code}` 并重定向至登录页 | 用户直接在官方页完成可行；第三方代提交仍属于代理登录风险 |
| 获取已登录用户的邀请码 | 官方文档确认推荐官页会展示邀请码、邀请链接和二维码 | **未找到公开 API**；只能在已登录官方页面中看到，第三方后端独立调用 No-Go |
| 邀请记录/注册状态/认证状态 | 官方文档和官方截图确认存在“我的邀请记录”，含账号 ID、注册时间、认证状态、是否有效认证；未登录页面整体 307 回登录 | **未找到公开 API 或授权范围**；无人值守后端查询 No-Go |
| 活动规则 | 2026-01-15 开始，持续至 2026-12-31；好友注册并实名认证后发券，1-5 分钟到账；重复认证不触发奖励 | 已证实 |

最关键判断：当前证据只能证明官方网页自己能够完成登录和展示邀请数据，不能证明第三方网站获准接收短信验证码、代理登录、保存官方会话或轮询内部邀请接口。官方隐私政策反而明确建议用户不要向任何人提供短信验证码、不要在非 `siliconflow.cn` 域名登录。因此，若产品硬性要求“客户在自建网站输入 SiliconFlow 验证码，后端自动获取邀请码并持续读取邀请/认证状态”，在未获得书面授权或正式 API 前应判定 **No-Go**。

## 已证实：登录和发送验证码

### 官方页面与保护机制

- 登录页：`https://account.siliconflow.cn/zh/login`
- 未登录访问 `https://cloud.siliconflow.cn/` 或推荐官页，会以 HTTP 307 重定向到统一登录域。
- 推荐官页的官方路径由官方文档直接给出：`https://cloud.siliconflow.cn/me/campaigns/inviter`。
- 登录和云平台响应均带 `X-Frame-Options: DENY` 及 `Content-Security-Policy: frame-ancestors 'none'`，不能把官方页嵌入本站 iframe。
- 登录与云平台页面均返回 `Cache-Control: no-cache, no-store, must-revalidate`。

### 发送验证码的公开前端协议

2026-08-14 下载到的官方登录页 Next.js chunk 中可以直接确认：

- 手机短信接口：`POST /api/open/sms`
- 邮件验证码接口：`POST /api/open/email`
- 手机注册/登录接口：`POST /api/open/login/user`
- 请求均由 `account.siliconflow.cn` 页面使用同源相对路径发出。
- 短信请求基础字段：`phone`、`area`，并合并易盾滑块校验返回值，附加 `captchaType: "yidun"`。
- 中国大陆区号在前端以 `area: "+86"` 传入。
- 验证码前端校验为 6 位数字。
- 发送成功后前端倒计时 60 秒。

短信发送前不是单一验证码，而是至少两层网易易盾依赖：

1. `initNECaptchaWithFallback` 弹窗滑块，前端可见 `captchaId: ed849b354a404ea8bef2e745352aa3cb`，成功结果中的动态校验对象被合并到短信请求。
2. 页面初始化 `createNEGuardian({ productId: "YD00578564041367", timeout: 6000 })`；最终登录前调用 `getToken()`，把所得 `token` 加进登录请求。

这意味着只模仿手机号和验证码两个字段不足以稳定复刻。动态校验值、设备环境、风控策略和接口契约都可能随时变化。

### 登录请求体形状

官方短信表单将下列字段提交给 `POST /api/open/login/user`：

```json
{
  "phone": "用户输入",
  "code": "6位短信验证码",
  "area": "+86",
  "shareCode": "可选邀请码",
  "keep": true,
  "token": "网易易盾 NEGuardian 动态 token",
  "utm_campaign": "可选",
  "oauthId": "可选",
  "prefix_link_key": "可选"
}
```

`shareCode` 在 UI 上最大长度为 8。官方邀请码链接使用 `invitation` 查询参数，例如登录页读取 `?invitation=...` 并回填 `shareCode`。官方短链形式已由响应验证为：

```text
https://cloud.siliconflow.cn/i/{邀请码}
  -> 307 https://account.siliconflow.cn/login
         ?redirect=https%3A%2F%2Fcloud.siliconflow.cn
         &invitation={邀请码}
```

登录成功后前端直接跳转 `redirect` 或 `https://cloud.siliconflow.cn`。登录响应/会话 cookie 的名称、属性和生命周期，因本次没有提交登录而**未知**；不能从静态代码推断“可保存 24 小时”。`keep: true` 只证明 UI 有“30 天内保持登录”选项，不证明第三方保存会话获授权。

只读 GET 请求这些 POST-only 接口均返回 405，从而不产生短信或登录行为：

- `GET https://account.siliconflow.cn/api/open/sms` -> 405
- `GET https://account.siliconflow.cn/api/open/login/user` -> 405
- `GET https://account.siliconflow.cn/api/open/email` -> 405

## 已证实：推荐官页面、邀请码和邀请记录字段

官方账户 FAQ 明确说明：

1. 电脑端登录 SiliconFlow。
2. 进入左侧“推荐官计划”，页面为 `https://cloud.siliconflow.cn/me/campaigns/inviter`。
3. 点击申请成为推荐官后，可以通过二维码、邀请码、邀请链接三种方式分享。
4. 邀请成功的具体信息显示在“我的邀请记录”。

官方 FAQ 附图显示：

- 推荐官页直接展示邀请码和 `https://cloud.siliconflow.cn/i/...` 邀请链接。
- “我的邀请记录”表头为：`账号 ID`、`注册时间`、`认证状态`、`是否有效认证`。
- 汇总展示“累计已完成 X 次有效推荐，共获得 Y 元代金券”。

字段语义结合活动公告可以证实为：

- `认证状态`：受邀账户当前是否已实名认证。
- `是否有效认证`：此次认证是否具备新邀请奖励资格；重复认证不会触发新的奖励。
- 活动成功条件：受邀好友完成注册且实名认证。
- 邀请券通常在好友注册认证后 1-5 分钟自动到账，因此记录状态不是严格实时事件流，业务系统需容忍至少这一结算延迟。

官方公开材料没有说明账号 ID 是否稳定、是否全局唯一、是否可与手机号映射，也没有说明分页、延迟、状态回退或记录保留期限。不能据截图擅自把账号 ID 当成本站唯一身份凭据。

## 已证实：活动期限与奖励规则

官方 2026-01-15 公告确认：

- 推荐官新计划自 2026-01-15 启动，持续至 **2026-12-31**。
- 推荐官需手动点击获得身份，分享专属邀请链接或邀请码。
- 好友注册并实名认证后，邀请双方各得 16 元通用代金券。
- 活动有效期内邀请人数不设上限。
- 邀请奖励通常在注册认证后 1-5 分钟到账。
- “重复认证”包括已经有效实名后修改、解绑重绑，或同一身份信息用于二次认证；重复认证不发新的邀请奖励。
- 代金券自获得之日起 180 天有效。
- 历史邀请链接对已认证用户仍可使用；未认证邀请人需先认证才具备邀请奖励资格。

由此可用于本站任务判断的官方业务事实只有：“已认证”不等于“有效认证”；发放 5 元前必须确认“是否有效认证”，否则会为重复实名错误付款。

## 鉴权与可调用边界

### 可以在用户明确授权下采用的方式

- 给用户生成官方邀请短链 `https://cloud.siliconflow.cn/i/{code}`，让用户在 `siliconflow.cn` 官方域完成注册、登录和认证。
- 让邀请人自行从官方推荐官页复制 8 位邀请码或邀请链接，粘贴到本站。
- 让用户主动提供官方页面导出的结果或脱敏截图，本站人工审核。
- 若 SiliconFlow 后续提供正式 OAuth/开放 API，按其授权范围和 token 生命周期接入；当前公开 API 文档中未发现推荐官、邀请记录或认证状态 API。

### 技术上可见但不应视为获准的方式

- 从本站后端直接调用 `/api/open/sms` 和 `/api/open/login/user`。
- 让用户在非官方域输入 SiliconFlow 短信验证码。
- 复制浏览器会话 cookie/token 到本站后端并保存、轮询。
- 反向工程已登录推荐官页面的内部请求、绕过易盾或模拟设备环境。

原因并非仅是稳定性：官方隐私政策明确建议“不向任何人提供短信验证码、不通过任何非 siliconflow.cn 域名网站登录”；用户协议要求用户不得泄露短信验证码等登录凭据，个人账户仅限本人使用，并禁止逆向、绕过访问限制、未经明确授权的使用方式。即便最终用户勾选本站授权，也不等于 SiliconFlow 授予本站调用其内部接口的权利。

## 推断与未知

### 合理推断（不能当作已验证事实）

- 登录成功大概率由 `.siliconflow.cn` 范围的 cookie 或等价服务端会话实现，因为账号域登录后跳到云平台域，配置中也存在 `COOKIE_DOMAIN: ".siliconflow.cn"`。本次未登录，未验证 cookie 名、HttpOnly/SameSite/Secure 属性。
- 推荐官页内部必然使用某种受登录态保护的数据接口来读取邀请码和记录，但它可能是 Next.js server action、BFF、GraphQL 或普通 REST；公开静态登录资源无法确定。
- 参考网站若能自动查询，可能持有用户官方会话并调用内部接口，也可能维护自己的抢单人状态；仅凭参考站 UI 不能证明其获得官方 API。

### 当前未知

- 获取邀请码、申请推荐官、邀请记录列表、有效认证状态的精确内部接口路径及请求/响应字段。
- 上述接口是否绑定 CSRF、Origin/Referer、设备指纹、易盾 token、签名或动态 header。
- 登录 cookie/token 的名字、作用域、刷新机制、撤销机制和真实有效期。
- 官方是否存在未公开的商业合作接口。
- 是否允许第三方代表用户保存会话和自动读取邀请记录；公开资料没有这种授权。
- 短信发送方号码 `10686303119360` 未在官方公开资料中找到，无法由本次官方一手资料验证；不能把该号码作为安全信任锚点。

### 未发现面向第三方的 OAuth/OIDC 或邀请开放 API

- 官方登录前端出现 Google、GitHub、微信入口及 `/api/open/oauth/google`、`/api/open/weixin`，语义是“SiliconFlow 作为客户端，使用第三方身份登录 SiliconFlow”，不是“SiliconFlow 作为授权服务器让本站读取用户邀请记录”。
- 对标准发现地址 `/.well-known/openid-configuration` 和 `/.well-known/oauth-authorization-server` 的只读访问均未返回 JSON 元数据，而是被站点语言/登录中间件重定向到 SiliconFlow 登录页。
- 当前官方 API Reference 公开的是模型、文件、批处理等开发者 API；未列出邀请码、推荐官、邀请记录、实名认证状态 scope 或端点。
- 因而截至验证日，**没有发现可供第三方应用使用的公开 OAuth/OIDC 授权流，也没有发现邀请/认证状态开放 API**。这只是对公开材料的结论，不排除 SiliconFlow 对签约合作方提供未公开接口。

## Go / No-Go

### 分项结论

- **Go：** 用户手动复制邀请码/邀请链接，本站生成任务，抢单人跳到官方页注册认证，本站人工审核官方记录。
- **Conditional Go：** 在用户自己浏览器中、明确操作下读取当前官方页面显示内容的辅助工具，但需要先取得 SiliconFlow 对自动读取的书面许可，并准备页面改版维护；仍不建议接触验证码或把会话上传后端。
- **No-Go：** 未获授权时在本站收集 SiliconFlow 验证码、后端代理登录、保存其官方会话 24 小时、无人值守调用内部邀请/认证接口。
- **No-Go：** 把当前可见前端路径包装成“开放 API”对外承诺稳定性。

### 对整体技术验证的门槛建议

进入生产开发前至少满足其一：

1. SiliconFlow 提供书面授权和正式接口，覆盖邀请码、邀请记录和“有效认证”状态；或
2. 产品接受客户手动粘贴邀请码，并把邀请结果改成人工/客户确认，不承诺无感自动监督。

在这两个条件都不满足时，上游集成应判定 **整体 No-Go**。开发任务大厅、计时、名额和人工支付宝付款本身可继续，但不能把付款触发建立在未经授权的 SiliconFlow 内部接口上。

## 可复现的只读命令

以下命令只做 GET/HEAD，不会发送验证码或登录。Windows PowerShell：

```powershell
# 登录页和响应头
curl.exe -sS -L -D sf-account-headers.txt `
  -o sf-account-login.html `
  https://account.siliconflow.cn/zh/login

# 推荐官页面未登录保护
curl.exe -sS -I `
  https://cloud.siliconflow.cn/me/campaigns/inviter

# 官方 FAQ 中确认推荐官页面路径和三种邀请方式
curl.exe -sS -L -o sf-account-faq.html `
  https://api-docs.siliconflow.cn/docs/userguide/faqs/misc_use
rg -n 'campaigns/inviter|邀请码|邀请链接|我的邀请记录' sf-account-faq.html

# 列出登录页公开 JS 资源
rg -o '/_next/static/[^? ]+[.]js' sf-account-login.html |
  Sort-Object -Unique

# 下载资源后定位登录接口与易盾字段（将 <js-dir> 替换为下载目录）
rg -n '/api/open/sms|/api/open/login/user|captchaType|createNEGuardian|shareCode' <js-dir>

# 只用 GET 验证接口是 POST-only，不触发短信
curl.exe -sS -X GET -D - -o NUL `
  https://account.siliconflow.cn/api/open/sms

# 邀请短链的公开重定向形状；请用自有邀请码替换 <code>
curl.exe -sS -I "https://cloud.siliconflow.cn/i/<code>"
```

本次保存的官方登录 HTML SHA-256：

```text
EE6CFE743BAA972EFF6E39A8CFD4162DE44C43537DE087AD539CE07C053A9D27
```

本次对应登录页主 chunk SHA-256：

```text
79CB58346F7BED558318BAC3AF91DA394DFD60626C5C8B679867184408B09A27
```

静态资源部署版本来自 webpack public path：`account-20260813-141723`。部署可随时变化，复验时 hash 不同并不必然代表异常。

## 官方一手来源

- SiliconFlow 统一登录：<https://account.siliconflow.cn/zh/login>
- SiliconFlow 账户 FAQ：<https://api-docs.siliconflow.cn/docs/userguide/faqs/misc_use>
- SiliconFlow 推荐官计划公告（2026-01-15）：<https://www.siliconflow.cn/developer-talk/od7wj9rr23p95uhihmhrombp>
- SiliconFlow 平台使用协议（更新日期 2026-05-22）：<https://api-docs.siliconflow.cn/docs/legals/terms-of-service>
- SiliconFlow 隐私政策（更新日期 2026-07-30）：<https://api-docs.siliconflow.cn/docs/legals/privacy-policy>
