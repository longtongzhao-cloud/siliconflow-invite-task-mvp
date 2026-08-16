# 参考站 SiliconFlow 链路只读技术审计

- 审计日期：2026-08-14（Asia/Shanghai）
- 目标：`http://tb.eq001.cn/choose/?source=5127688621175028142&step=0&type=gjld`
- 范围：公开页面、公开前端 JavaScript、匿名 GET/SSE 响应、只读浏览器运行态
- 未执行：发送短信、填写或提交验证码、操作滑块、注册/登录、实名认证、创建或确认订单、调用任何已知写端点
- 前端包：`http://tb.eq001.cn/assets/index-DMGl4aIs.js`
- 审计时包长度：401,595 字符（PowerShell `Invoke-WebRequest` 解码后）
- SHA-256：`2a04d95e120c163ca6943f4b2ab7519d3d5b7d858628a1e28a1484845c47ab4e`

## 1. 结论摘要

参考站不是通过“手机号公开查询接口”取得邀请码。公开前端显示，它把手机号、短信验证码、滑块结果和淘宝订单号提交到参考站后端；参考站后端完成登录代理后返回 8 位邀请码，再由用户确认绑定到订单。目标人数、已注册数和已认证数由参考站自己的 `/gjld/task/config` 接口直接汇总返回。

抢单人侧是另一套登录/注册链路：指定邀请码位于路径中，手机号和短信验证码提交到参考站后端后，后端返回 `sToken`；个人中心再用带凭据 SSE 或带 `sToken` 请求读取 `passportId` 与 `authInfo`。`authInfo` 至少包含 `isAuth`、`authTime`、`isSystem`、`isFirstAuth`、`authStatus` 等前端使用字段，可区分未认证、有效首次认证和重复/非首次认证。

因此，目标功能在工程上有可复制的架构形态，但本次只读验证没有、也不能证明：参考站调用的 SiliconFlow 上游私有接口名称、会话有效期、风控稳定性，以及无官方授权时该方案能否长期运行。进入正式开发前仍必须用自有测试手机号和明确授权的测试账号做一次端到端封闭验证。

## 2. 已证实事实

### 2.1 页面与后端分离

- `tb.eq001.cn` 返回 Vue 单页应用壳，主要脚本为 `/assets/index-DMGl4aIs.js`。
- 业务接口均指向 `https://p2.eq001.cn`，浏览器请求设置跨域凭据。
- 样例配置响应带：`Access-Control-Allow-Origin: http://tb.eq001.cn` 和 `Access-Control-Allow-Credentials: true`。

### 2.2 客户获取邀请码及绑定订单

目标 `type=gjld` 表单公开代码定义请求数据：

```json
{
  "phone": "<11位手机号>",
  "code": "<6位验证码>",
  "inviteUrl": "<可选的 SiliconFlow 邀请链接>",
  "orderNo": "<URL source 参数>"
}
```

前端流程：

1. 首屏可选“手机号.验证码”或“填写邀请链接”。只读运行态确认了这两个入口。
2. 手机号步骤调用滑块组件，目标端点为 `https://p2.eq001.cn/captcha/setPhone`。滑块插件在 `validCaptcha` 前把上述请求数据合并进请求。
3. 验证码步骤先调用 `https://p2.eq001.cn/gjld/captcha/valid` 校验滑块。
4. 滑块成功后，前端明确执行：

```http
POST https://p2.eq001.cn/captcha/login
Content-Type: application/json

{
  "phone": "...",
  "code": "...",
  "id": "<滑块校验返回值>",
  "orderNo": "5127688621175028142"
}
```

5. 前端期望登录响应的形状为：外层 `code === 200`，内层 `data.code === 0`，内层 `data.data` 是邀请码；随后弹框展示“是否确认邀请码”。
6. 用户确认后，前端执行 `POST /gjld/user/confirm`，请求体为淘宝订单号；这是把已取得的邀请码确认到订单的写操作，本次未调用。
7. 手工邀请链接校验规则为 `https://cloud.siliconflow.cn/i/<字母数字>`。

这证明邀请码是登录代理结果，不是只凭手机号匿名查询。短信实际由谁发送、参考站后端调用哪个 SiliconFlow 上游接口，前端包不包含该信息。

### 2.3 抢单人注册/登录及会话

公开路由：

- `/v/:inviteCode`：前端组件名 `SiliconflowMiniPrograme`
- `/au/:inviteCode`：前端组件名 `SiliconflowAuthLogin`
- `/a/zh/user/settings`：个人中心
- `/a/account/authentication`：认证页面

两种登录入口均带指定邀请码，且有滑块、短信和验证码链路：

| 用途 | 方法与端点 | 请求字段 |
|---|---|---|
| `/v/:inviteCode` 发送验证码 | `POST /gjld/captcha/sendCode` | `phone`, `platform`, `id`, `checkExist` |
| `/au/:inviteCode` 发送验证码 | `POST /gjld/captcha/auth/sendCode` | `phone`, `platform`, `id`, `checkExist` |
| `/v/:inviteCode` 注册/登录 | `POST /gjld/captcha/i/:inviteCode` | `phone`, `platform`, `code`, `id` |
| `/au/:inviteCode` 登录/助力 | `POST /gjld/captcha/a/:inviteCode` | `phone`, `platform`, `code`, `id` |

注册/登录成功后，前端预期 `data.data` 为 `sToken`，并执行：

- `localStorage.setItem("sToken", token)`；
- 尝试设置名为 `sToken` 的 Cookie，有效期参数为 1 天；
- `localStorage.setItem("loginPhone", phone)`；
- 跳转 `/a/zh/user/settings`。

个人资料存在两条读取路径：

1. 首选 `GET https://p2.eq001.cn/gjld/profile/stream`，`EventSource(..., {withCredentials: true})`；
2. 备用 `GET https://p2.eq001.cn/gjld/profile`，同时发送跨域凭据及请求头 `sToken: localStorage.getItem("sToken")`。

匿名只读验证结果：

```text
GET /gjld/profile
200 application/json
{"code":500,"msg":"未登录!"}

GET /gjld/profile/stream
200 text/event-stream
event:error
data:登录令牌为空!
```

这证明个人资料和认证状态需要会话，而不是公开查询。

### 2.4 用户与认证状态字段

SSE 前端处理阶段及字段：

- `stage: "base_info"`：合并 `passportInfo`、`subjectInfo`；
- `stage: "auth_info"`：读取 `authInfo`；
- `stage: "complete"`：完成；
- `stage: "error"`：业务错误。

前端模型明确包含：

```json
{
  "passportId": "",
  "name": "",
  "phone": "",
  "countryCode": "",
  "createTime": "",
  "authInfo": {
    "isAuth": false,
    "authTime": null,
    "isSystem": false,
    "isFirstAuth": false,
    "authStatus": null
  }
}
```

界面分支使用 `isSystem`、`authStatus === 1` 和 `isFirstAuth === true` 展示“已认证 / 重复认证 / 非首次认证”。截图中的“用户 ID、注册时间、认证状态、是否有效认证”与这套字段吻合。

### 2.5 任务配置与计数来源

首页加载时直接调用：

```http
GET https://p2.eq001.cn/gjld/task/config?tid=<source>
```

2026-08-14 对用户给定样例订单的匿名只读响应为：

```json
{
  "needNum": 5,
  "isEnableUidInvite": true,
  "uidList": [
    {
      "phone": "<报告中已脱敏>",
      "shareId": "<8位邀请码已脱敏>",
      "time": "Aug 13, 2026 11:39:40 PM"
    }
  ],
  "regNum": 2,
  "authNum": "1",
  "shareId": "<8位邀请码已脱敏>",
  "inviterPhone": "<报告中已脱敏>"
}
```

前端直接映射：

- 目标邀请人数 = `needNum`
- 已注册/已邀请人数 = `regNum`
- 已认证人数 = `authNum`
- 剩余次数 = `needNum - regNum`
- 邀请码 = `shareId`，缺失时回退到 `uid` 或 `uidList[0].shareId`

因此，三个计数的直接来源已证实是参考站后端的 `task/config` 聚合响应，而不是客户浏览器临时打开 SiliconFlow“我的邀请记录”页面。

当前样例响应没有独立 `taskStatus` 字段。前端可用 `needNum/regNum/authNum` 推导进度，但是否另有后端订单状态、何时关单、按注册数还是认证数关单，公开代码和本次响应均未证实。

### 2.6 公开配置泄露

`task/config` 无需登录即可返回完整邀请人手机号和邀请码，且 `tid` 直接使用订单号。这是参考站自身的隐私/越权风险，不应照搬。新系统必须使用不可枚举的签名任务 ID，并对外脱敏手机号；管理接口另行鉴权。

## 3. 高可信推断（非直接证实）

1. 参考站后端持有或代理 SiliconFlow 登录会话。依据是 `/captcha/login` 能返回邀请码，抢单登录端点能返回 `sToken`，资料端点凭 `sToken` 返回 SiliconFlow 风格的用户/认证字段。
2. `regNum` 很可能是参考站在指定邀请码注册链路中记录的成功用户数；`authNum` 很可能由这些用户的 `authInfo` 更新汇总。但公开前端不能证明聚合 SQL、去重键、刷新任务或重试策略。
3. `passportId` 很可能是截图所示 SiliconFlow 用户 ID，可作为站内参与记录的外部主体标识；仍需端到端测试确认其稳定性和唯一性。
4. `isFirstAuth`、`isSystem`、`authStatus` 的组合很可能用于判断“有效首次认证”。前端展示逻辑不完全等同于业务结算逻辑，正式实现需要用测试账号验证每种状态转换。
5. 客户邀请码获取流程可能将临时登录态保存在参考站服务端或跨域 Cookie 中，再由 `/gjld/user/confirm` 绑定订单。该流程的浏览器代码没有把 token 显式写入客户页面存储，所以精确会话载体未知。

## 4. 未知与技术验证缺口

- SiliconFlow 上游的真实 API 路径、请求头、Cookie 名称和响应结构；这些均藏在参考站服务端。
- 短信是否始终由 `10686303119360` 发送；公开前端无法证明发送方号码。
- 参考站是否保存用户短信验证码、会话令牌和认证资料，以及保存时长、加密和删除策略。
- `sToken` 是否等同 SiliconFlow 原生会话、参考站自签代理令牌，还是二者的映射键。
- Token 的真实服务端寿命。前端 Cookie 的 `expires: 1` 只能证明客户端意图为 1 天，不能证明上游有效期。
- `regNum` 的精确定义：登录成功、注册成功、确认绑定成功还是产生邀请关系。
- `authNum` 的精确定义及延迟：`isAuth`、`isFirstAuth`、`authStatus` 哪一组合才计数。
- 同一身份证、手机号、微信、支付宝、设备的跨账号去重能力。公开链路最多能观察手机号和 SiliconFlow 用户/认证结果。
- 订单的关闭条件、24 小时有效期、抢单租约和并发名额。参考站公开代码没有用户所需的 30 分钟抢单租约。
- 上游页面或私有接口变更后的稳定性与风控封禁概率。

## 5. 对自建 MVP 的最低验证门槛

在得到自有测试手机号持有人的明确授权后，使用隔离测试订单完成一次人工端到端验证，且不复用参考站私有后端：

1. 已注册且开启推荐官的测试客户完成短信登录，确认能稳定取得 8 位 `shareId`。
2. 新手机号通过 `https://cloud.siliconflow.cn/i/<shareId>` 注册，确认邀请关系绑定到指定客户。
3. 分别采集“未认证、首次有效认证、重复/非首次认证”的最小状态字段，核定结算布尔表达式。
4. 轮询或事件读取持续 30 分钟，测量认证状态延迟、会话过期和重登要求。
5. 关闭浏览器并恢复会话，确认加密保存的服务端会话可用且 24 小时后不可用。
6. 用并发测试确认 `N` 个名额、超时释放和最后一名奖励资格通过数据库事务保持一致。

若第 1 至 3 项无法通过正式授权接口或稳定的用户授权会话实现，应停止自动化方案，回退到用户手工粘贴邀请码与人工审核。

## 6. 可复现的只读命令

以下命令只执行 GET，不会发送短信、提交验证码或写订单。

```powershell
$page = Invoke-WebRequest -Uri 'http://tb.eq001.cn/choose/?source=5127688621175028142&step=0&type=gjld' -UseBasicParsing
$page.StatusCode
$page.Content
```

```powershell
$js = (Invoke-WebRequest -Uri 'http://tb.eq001.cn/assets/index-DMGl4aIs.js' -UseBasicParsing).Content
[regex]::Matches($js, 'https://p2\.eq001\.cn/gjld/[A-Za-z0-9_?&=./:${}\-]+') |
  ForEach-Object Value |
  Sort-Object -Unique
```

```powershell
Invoke-WebRequest `
  -Uri 'https://p2.eq001.cn/gjld/task/config?tid=5127688621175028142' `
  -Headers @{ Origin='http://tb.eq001.cn'; Referer='http://tb.eq001.cn/' } `
  -UseBasicParsing |
  Select-Object StatusCode, Content
```

```powershell
Invoke-WebRequest `
  -Uri 'https://p2.eq001.cn/gjld/profile' `
  -Headers @{ Origin='http://tb.eq001.cn'; Referer='http://tb.eq001.cn/' } `
  -UseBasicParsing |
  Select-Object StatusCode, Content
```

```powershell
Invoke-WebRequest `
  -Uri 'https://p2.eq001.cn/gjld/profile/stream' `
  -Headers @{ Origin='http://tb.eq001.cn'; Referer='http://tb.eq001.cn/' } `
  -UseBasicParsing |
  Select-Object StatusCode, Content
```

注意：样例 `task/config` 当前公开泄露手机号。复现时不要把原始响应粘贴到工单、聊天或版本库；本报告已脱敏。

## 7. 本次验证判定

| 验证目标 | 判定 | 说明 |
|---|---|---|
| 参考站能展示订单对应 8 位邀请码 | 已证实 | `task/config.shareId` 当前返回 8 位值 |
| 参考站通过手机号+验证码获取邀请码 | 前端协议已证实，端到端未执行 | 明确存在 `/captcha/login` 及响应读取逻辑 |
| 指定邀请码进入抢单人注册链路 | 已证实 | `/v/:inviteCode`、`/au/:inviteCode` 路由及注册端点 |
| 读取用户 ID 与认证字段 | 协议已证实，登录态响应未采样 | `profile/stream` 和 `profile`；匿名请求明确拒绝 |
| 区分首次有效与重复认证 | 前端字段/显示逻辑已证实，结算语义待实测 | `isFirstAuth/isSystem/authStatus` |
| 获取目标数、注册数、认证数 | 已证实 | `task/config` 匿名响应及前端映射 |
| 独立任务状态字段 | 未证实 | 当前响应无 `taskStatus/status` |
| 不依赖客户反复查看邀请记录 | 架构上成立 | 参考站后端聚合；自建系统仍需持有抢单人授权会话 |
| 可稳定生产复刻 | 尚未通过 | 缺少官方接口、上游协议和授权账号端到端验证 |
