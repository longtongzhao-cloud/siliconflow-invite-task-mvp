# 手机真人浏览器接力网关契约

当前状态：应用侧失败关闭边界已完成，真实网关未实现，`MVP_REMOTE_BROWSER_MODE` 必须保持 `disabled`。

## 目标流程

1. 客户从订单页明确同意一次性接力。
2. 应用创建最长 5 分钟的接力记录并在事务提交后调用 broker。
3. broker 为该订单启动隔离 Chromium，固定导航到 SiliconFlow 官方登录页。
4. 客户通过独立的 HTTPS viewer 在手机完成 CAPTCHA 和 OTP；应用页面不得收集答案。
5. 受信 runner 登录成功后读取最小邀请信息，通过签名回调提交结果。
6. 应用再次检查订单状态，原子保存邀请码及最长 24 小时的加密上游会话。
7. 完成、取消、超时、退款或异常均触发浏览器和临时 profile 销毁；失败销毁进入重试队列。

## 状态机

```text
STARTING -> AWAITING_USER -> PROCESSING -> COMPLETED
    |              |             |
    +--------------+-------------+-> FAILED
                   +---------------> CANCELLED
                   +---------------> EXPIRED
```

终态不可恢复。会话空闲截止时间等于 `created_at + 300`；任何活动都不能延长订单的 24 小时截止时间。

## 对外接口

当前已有：

- `POST /api/customer/{customer_token}/silicon/handoffs`
- 请求：`{"consent": true}`
- 未配置时：HTTP 503，错误码 `REMOTE_BROWSER_DISABLED`，不得写入 consent 或 handoff 记录。

网关完成后，启动响应应为：

```json
{
  "session_id": "handoff_...",
  "viewer_url": "https://viewer.example/session/...",
  "expires_at": 0
}
```

`viewer_url` 必须使用一次性随机凭据；浏览器首次兑换后改用 HttpOnly、Secure、SameSite Cookie。不得在 URL 中放置 OTP、Cookie、SiliconFlow 会话或手机号。

后续需要实现同一客户 token 下的状态查询和取消接口。跨订单、跨客户 token 和抢单人会话访问统一返回 404。

## Runner 回调

回调只接受 broker 服务身份，至少包含：事件 ID、handoff ID、时间戳、结果摘要和 HMAC 签名。要求：

- 时间窗不超过 60 秒；事件 ID 防重放；同 ID 不同载荷返回冲突。
- 回调时订单必须仍为 `AWAITING_INVITE` 或 `ACTIVE` 且未过期。
- 邀请码必须通过既有 8 位邀请码解析器。
- 上游会话只进入 AES-GCM 密文列，截止时间取上游期限、订单期限和 24 小时上限的最小值。
- 事务成功后撤销 viewer；事务失败不得留下半激活订单。

## 网关安全边界

- 每个 handoff 独立容器、用户目录和下载目录；容器内不得挂载应用密钥或数据库。
- 只允许导航到明确的 SiliconFlow 官方域名，不开放任意 URL、DevTools、文件上传或下载。
- CAPTCHA 必须由客户本人操作；禁止 OCR 自动点击、打码平台、设备指纹伪造和无限重试。
- 禁止录屏以及记录 OTP、点击坐标、Cookie、Authorization、请求体和浏览器 profile。
- 同一订单最多一个活跃 handoff；启动、viewer 兑换和回调都需限流。
- broker 网络调用必须发生在 SQLite/PostgreSQL 事务外。

## 启用门槛

- SiliconFlow 对代理登录、会话保存和邀请记录读取的明确许可。
- 独立 HTTPS 域名、服务器、防火墙和受信 broker 身份。
- 390×844 手机视口完成 CAPTCHA、切换短信应用、返回重连和取消测试。
- 完成并通过一次性 token、并发唯一、5 分钟边界、退款竞态、回调验签、防重放、密文和销毁重试测试。
- 手动邀请码流程保持可用，并提供一键关闭新接力会话的运营开关。
