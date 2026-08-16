# Project Status

最后核对日期：2026-08-16  
当前阶段：本地 MVP 已通过；生产外部接入未通过。  
仓库根目录：`outputs/`  
应用目录：`outputs/mvp/`

## 当前目标

构建一个从淘宝订单到任务结算的邀新任务系统：淘宝 SKU 对应 1/5/10 个有效完成者；客户提供 SiliconFlow 邀请信息后生成任务链接；抢单人完成本站手机号登录和支付宝收款信息登记，领取 30 分钟保护名额，并在订单 24 小时有效期内完成 SiliconFlow 新用户注册、填写邀请码和首次有效实名认证；系统最多锁定 N 份 5 元奖励，第一版由管理员人工支付宝转账。

当前可执行目标是把已通过的本地 MVP 推进到可公网访问的测试环境，并分别完成 SiliconFlow 真实代理登录、淘宝订单权限和本站真实短信的受控端到端验证。生产上线不是当前已完成状态。

## 已完成内容

### 可运行 MVP

- FastAPI + SQLite 后端和原生 HTML/CSS/JavaScript 前端。
- 管理员按淘宝订单号、`outer_sku_id` 和数量创建订单；`SF_INVITE_1/5/10` 映射到 1/5/10 人。
- 客户订单链接、8 位邀请码/官方邀请链接手动录入，以及不联网的 mock 代理登录流程。
- 本站手机号登录、支付宝收款信息登记、公开任务大厅、抢单、我的任务和站内通知。
- 30 分钟保护、15 分钟提醒、24 小时订单截止、超时补做和无候补规则。
- 首次有效认证后创建 5 元奖励；待支付、支付重试和已支付均占用锁定容量；人工登记唯一支付流水号。
- 淘宝 mock 付款事件幂等、全额退款/关闭处理；真实淘宝 webhook 默认返回禁用错误。
- SiliconFlow `mock`、`manual`、`live-disabled` 三种适配器模式；没有可由普通环境变量启用的真实适配器。
- 手机号 HMAC 索引和掩码、支付宝及上游会话 AES-256-GCM 加密、会话最长 24 小时及过期/退款/关闭删除。

### 技术验证材料

`../tech-validation/` 包含参考站只读协议审计、SiliconFlow 官方客户端审计、淘宝/经营主体核验、安全 QA、业务规则与并发探针、会话安全测试、现场测试手册和汇总报告。探针默认只做 GET/HEAD，不发送短信、不提交 OTP、不登录、不注册、不实名、不支付。

## 关键技术决策

1. **外部系统适配器隔离**：业务状态机不依赖网页私有接口字段。开发演示用 `mock`，无网络人工流程用 `manual`，生产默认 `live-disabled`；取得可测试条件后新增独立 live 实现。
2. **名额以数据库为真源**：SQLite 事务使用 `BEGIN IMMEDIATE` 串行化竞争，始终保持 `reward_locked + active_reservations <= target_n`。前端倒计时不参与结算。
3. **固定时间语义**：`reservation_expires_at = claimed_at + 30m`；等于截止时刻即超时。`order_expires_at = paid_at + 24h`，登录和重试不能延期。
4. **超时补做不侵占保护名额**：只有 `locked + active < N` 时，超时完成者才能锁定奖励；否则记录为完成但无奖励。
5. **奖励与支付幂等**：一个 assignment 只能有一个 reward；上游用户键和支付流水号全局唯一；支付未成功不释放资格。
6. **数据最小化**：不采集身份证、人脸或证件照片。OTP 仅在单次请求内使用；手机号和支付宝使用独立 HMAC 索引；需回显的数据才加密保存。
7. **会话只在服务端**：上游 token 不返回浏览器；AES-GCM AAD 绑定记录、订单、用户引用和到期时间。生产密钥必须迁移到独立 KMS。
8. **当前存储只适合单机 MVP**：SQLite 用于本地验证；公网多实例或正式运营前迁移 PostgreSQL，并引入数据库迁移工具和备份恢复流程。
9. **界面定位为运营工具**：客户页、任务页和管理台直接呈现业务状态；已验证桌面和 390px 移动端，无营销落地页。

## 核心文件

| 文件 | 作用 |
|---|---|
| `mvp_app/main.py` | FastAPI 路由、认证、订单、抢单、奖励、人工支付、Taobao mock/webhook 安全开关 |
| `mvp_app/database.py` | SQLite schema、事务连接、提醒/过期扫描、容量统计、演示数据 |
| `mvp_app/adapters.py` | SKU 映射、邀请码校验、SiliconFlow mock/manual/live-disabled 适配器 |
| `mvp_app/security.py` | HMAC、AES-GCM、站内会话签名、数据掩码 |
| `static/index.html` | 单页应用外壳和登录/支付宝对话框 |
| `static/app.js` | 客户、抢单人和管理员端交互 |
| `static/styles.css` | 桌面/移动响应式样式 |
| `tests/test_mvp.py` | 16 项 API、并发、安全和生命周期测试 |
| `run.ps1` / `run-tests.ps1` | 本地启动和复验入口 |
| `run.sh` / `run-tests.sh` | Linux/macOS 启动和复验入口 |
| `requirements.txt` / `requirements-dev.txt` / `.env.example` | 运行依赖、开发测试依赖和非敏感配置模板 |
| `README.md` / `MVP-STAGE-REPORT.md` | 使用说明和阶段验收结论 |
| `USER_GUIDE.md` | 管理员、客户和抢单人的当前 MVP 操作手册及生产边界 |
| `../tech-validation/validation-report.md` | 外部协议、风险和 Go/No-Go 总结 |
| `../README.md` / `../DEPENDENCIES.md` | GitHub 仓库入口和依赖边界 |
| `../CONTRIBUTING.md` / `../SECURITY.md` | 协作流程和安全要求 |
| `../.github/workflows/ci.yml` | Python 3.12/3.13 的 GitHub CI |

生成文件 `data/mvp.db`、`.pytest_cache/` 和 `__pycache__/` 不属于源代码，建立 Git 仓库时应忽略。

## 测试与验证结果

2026-08-16 在当前工作区重新执行：

```powershell
cd outputs\mvp
powershell -ExecutionPolicy Bypass -File .\run-tests.ps1
```

仓库整理并升级依赖后的最终结果：`16 passed in 6.95s`，无测试警告。覆盖：

- mock 代理登录、会话密文检查、邀请码返回、抢单、认证、奖励和支付完整闭环；
- SKU 1/5/10 映射；登录和支付宝前置条件；
- N=1/5/10 实际 API 并发不超额及重复抢单幂等；
- 超时补做有空位获奖、不得侵占活跃保护位、24 小时截止；
- 15 分钟提醒幂等、过期会话删除；
- 淘宝 mock 付款幂等、退款关闭、真实 webhook 失败关闭；
- SiliconFlow 真实适配器失败关闭。

同日执行 `../tech-validation/run-validation.ps1`：

- 只读端点模式：23 个；未触发 SMS、OTP、CAPTCHA、订单或支付动作；
- 业务规则：5/5；
- 并发模型：6/6；
- 合成会话安全：8/8；
- Markdown/JSON 敏感输出扫描：13 个文件通过。

此前浏览器验收已覆盖任务大厅、客户代理登录 mock、抢单、认证、管理台、桌面和 390px 移动端；无横向溢出，控制台 0 个错误/警告。本次核对时本地服务未运行，使用 `run.ps1` 启动。

## Git 状态

仓库根目录为 `outputs/`，包含应用与技术验证包。已在该目录初始化 `main` 分支，并添加 `.gitignore`、`.gitattributes`、`.editorconfig`、依赖说明、贡献指南、安全说明、PR 模板和 GitHub CI。GitHub 私有仓库为 `longtongzhao-cloud/siliconflow-invite-task-mvp`，首个基线提交和推送于 2026-08-16 完成。

`git add --dry-run .` 已确认候选列表只包含源码、测试、文档和仓库配置；`mvp/.venv/`、`mvp/data/mvp.db`、缓存和 `tech-validation/evidence/*.json` 均被忽略。

仓库整理时使用 `pip-audit` 发现旧版 `cryptography`、`pytest` 和 FastAPI 间接依赖 Starlette 存在已知漏洞，因此已升级并显式固定安全版本。升级后 `pip check` 返回 `No broken requirements found`，`pip-audit` 返回 `No known vulnerabilities found`；GitHub CI 会继续执行依赖漏洞审计。

应用代码没有 Windows 专用运行时依赖。仓库已补充 Bash 入口，技术验证脚本已消除对子进程命令 `powershell` 的硬编码，GitHub CI 覆盖 Ubuntu/Windows 与 Python 3.12/3.13。当前电脑没有 WSL 或 Docker，因此 Linux 实机结果以 GitHub Ubuntu CI 为准。

## 已知问题与外部阻塞

### SiliconFlow

- 尚未提交真实 SiliconFlow OTP，真实 cookie/token 名称、生命周期、邀请记录请求和认证字段未端到端验证。
- 官方前端存在网易易盾滑块/设备令牌；当前没有 CAPTCHA 人工接力实现，也不能自动绕过。
- 未发现供第三方使用的推荐官/邀请记录 OAuth 或开放 API。公开协议审计只证明网页内部流程存在，不证明稳定性或平台授权。
- 产品要求是代理登录并保存会话最长 24 小时；产品负责人希望把用户勾选视为委托依据。现有报告仍区分“用户授权本站操作”和“SiliconFlow 授权第三方接口”，不能对外宣称官方接入。
- 尚未用真实新用户完成“未注册 -> 已注册未实名 -> 首次有效实名”三阶段样本，也没有合法的重复/无效认证样本；自动判奖不能视为生产通过。

### 淘宝

- 没有 AppKey/API 权限、OAuth Access Token、订单消息订阅或店铺授权的可用验证结果。
- `taobao.trade.fullinfo.get`、付款/关闭/退款消息、购后卡片和聊天发送均未端到端测试。
- 当前官方“应用软件开发商”和“自研商家”接入指南都要求企业身份和企业资料。现有个人开发者认证不等于该应用类目的生产权限；未确认个人店铺能获得所需能力。
- 第一版只能人工创建订单并发送客户链接；代码仅实现全额退款/关闭，未实现部分退款按有效件数缩容。

### 部署、账号与运营

- 尚无公网域名、HTTPS 服务器、生产数据库、KMS、管理员 MFA、备份恢复和监控告警。
- 候选域名未购买；`gjlt.com` 已被注册，其他候选在购买前必须重新查询实时状态和商标/混淆风险。
- 本站登录仍是开发演示验证码。普通阿里云短信签名需要企业资质；个人主体可评估阿里云号码认证服务的“短信认证”产品。
- 支付宝仅登记收款信息，未验证账户归属；尚未执行真实 5 元转账或对账。
- 管理员认证、Cookie 安全参数和本地默认配置只适合开发环境，不能直接公网部署。

## 尝试过但未形成可用方案

1. **匿名手机号直接查询邀请码**：参考站实际是验证码后代理登录，不是匿名查询；该假设已排除。
2. **直接复刻 SiliconFlow 网页接口作为开放 API**：能看到登录端点和前端字段，但存在易盾、设备令牌、私有契约和授权/稳定性缺口；未实现 live 调用。
3. **通过标准 OAuth/OIDC 获取 SiliconFlow 邀请数据**：公开 discovery 和 API Reference 未发现邀请/认证 scope 或端点。
4. **用淘宝个人开发者认证直接取得订单权限**：当前应用软件开发商及自研商家指南要求企业身份/资料，尚未得到 `trade.fullinfo.get` 或消息订阅权限。
5. **自动通过淘宝聊天发送动态外链**：未发现当前账号已有专项能力，MVP 保留人工复制发送。
6. **本地电脑承接生产回调**：可以开发和受监督联调，但没有稳定公网 HTTPS 地址，不能作为 7x24 淘宝 webhook 和客户访问方案。
7. **普通阿里云短信自用签名**：个人主体无法完成当前运营商实名报备；应改用免企业资质的短信认证产品或后续企业资质。

## 下一步开发顺序

1. **配置 GitHub 协作保护**：为 `main` 启用 PR、CI 和至少一名审查者要求，启用私密漏洞报告，并邀请实际协作者；仓库转为公开前先确定许可证和对外披露范围。
2. **锁定淘宝落地路线**：在“申请满足平台要求的经营主体并申请 API”与“长期人工建单/发链接”之间做决定。未解决前不开发淘宝 live 适配器。
3. **准备测试部署**：重新查询并购买中性、非官方混淆域名；购买满足预算的轻量服务器；配置 Ubuntu、DNS、HTTPS、反向代理、防火墙和独立测试数据库。中国香港节点可用于快速联调，内地正式服务另行处理备案和网络质量。
4. **接入本站真实短信**：优先验证阿里云号码认证服务的短信认证；将固定演示验证码替换为发送/核验 API、限流和回执处理。
5. **生产化基础设施**：SQLite 迁移 PostgreSQL；引入 schema migration、KMS/密钥轮换、管理员 MFA/RBAC、审计、备份恢复、错误监控和一键冻结开关。
6. **淘宝接入（满足权限后）**：完成 OAuth、店铺主账号授权、`trade.fullinfo.get` 最小字段读取、付款/关闭/退款消息验签与幂等；先保留人工链接发送，再单独申请卡片/聊天能力。
7. **SiliconFlow 受控 live 验证**：使用专用邀请人账号，由账号本人解决 CAPTCHA 并输入 OTP；实现会话 Vault、字段 schema 校验、401/403/429/5xx 熔断和人工回退；禁止验证码/令牌日志。
8. **真人三阶段验收**：使用一个全新用户依次验证注册前、注册未实名、首次有效实名；人工对照官方邀请记录，测量状态延迟。无法获得重复/无效样本时保持人工判奖。
9. **支付与争议闭环**：执行一笔受控 5 元人工转账，验证流水幂等、支付失败不释放容量、隐私遮罩、对账和申诉处理。
10. **上线门复测**：重跑全部 P0 并发、安全、删除、外部失败和浏览器测试；真实写接口、真实支付与用户数据测试必须单独留存脱敏证据。

## 继续工作的入口

- 本地启动：`powershell -ExecutionPolicy Bypass -File .\run.ps1`
- MVP 测试：`powershell -ExecutionPolicy Bypass -File .\run-tests.ps1`
- Linux/macOS 启动：`./run.sh`
- Linux/macOS 测试：`./run-tests.sh`
- 技术验证：在 `../tech-validation/` 执行 `powershell -ExecutionPolicy Bypass -File .\run-validation.ps1`
- 阶段结论：`MVP-STAGE-REPORT.md`
- 当前版本使用说明：`USER_GUIDE.md`
- 外部接口与风险总览：`../tech-validation/validation-report.md`
- 真人现场步骤：`../tech-validation/live-test-runbook.md`

所有真实 AppSecret、Access Token、OTP、会话令牌和支付凭据只能通过部署环境的密钥管理配置，不得写入仓库、交接文档、日志或聊天。
