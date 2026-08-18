# Project Status

最后核对日期：2026-08-18
当前阶段：本地 MVP、WSL 临时公网 mock 链路与测试部署资产已通过；稳定公网和生产外部接入未通过。
仓库根目录：`outputs/`  
应用目录：`outputs/mvp/`

## 当前目标

构建一个从淘宝订单到任务结算的邀新任务系统：淘宝 SKU 对应 1/5/10 个有效完成者；客户提供 SiliconFlow 邀请信息后生成任务链接；抢单人完成本站手机号登录和支付宝收款信息登记，领取 30 分钟保护名额，并在订单 24 小时有效期内完成 SiliconFlow 新用户注册、填写邀请码和首次有效实名认证；系统最多锁定 N 份 5 元奖励，第一版由管理员人工支付宝转账。

当前可执行目标是先采用人工淘宝运营：人工确认付款、人工建单并发送客户链接，不开发淘宝 live 适配器。购买域名和云服务器前，先用 WSL + Cloudflare Quick Tunnel 的临时 HTTPS 地址完成三角色手机端受控联调；只有流程被人工验收、确实需要固定地址和持续在线后再购买资源。随后完成 SiliconFlow 真实代理登录和本站真实短信的受控端到端验证。生产上线不是当前已完成状态。

## 已完成内容

### 可运行 MVP

- FastAPI + SQLite 后端和原生 HTML/CSS/JavaScript 前端。
- 管理员在人工确认淘宝付款后，按订单号、`outer_sku_id` 和数量建单并复制专属客户链接；`SF_INVITE_1/5/10` 映射到 1/5/10 人，整个流程不需要淘宝 API。
- 客户订单链接、8 位邀请码/官方邀请链接手动录入，以及不联网的 mock 代理登录流程。
- 本站手机号登录、支付宝收款信息登记、公开任务大厅、抢单、我的任务和站内通知。
- 公开任务仅展示条件；邀请码和官方链接只在抢单成功后通过本人会话返回，不能绕过 N 人名额直接取得。
- 抢单人可在手机打开官方邀请页并提交 SiliconFlow 用户 ID；ID 使用 AES-GCM 密文和 HMAC 保存，仅进入待核验状态，不直接发奖。
- 30 分钟保护、15 分钟提醒、24 小时订单截止、超时补做和无候补规则。
- 首次有效认证后创建 5 元奖励；待支付、支付重试和已支付均占用锁定容量；人工登记唯一支付流水号。
- 淘宝 mock 付款事件幂等、全额退款/关闭处理；真实淘宝 webhook 默认返回禁用错误。
- SiliconFlow `mock`、`manual`、`live-disabled` 三种适配器模式；没有可由普通环境变量启用的真实适配器。
- 手机号 HMAC 索引和掩码、支付宝及上游会话 AES-256-GCM 加密、会话最长 24 小时及过期/退款/关闭删除。
- 集中式运行配置；生产启动会拒绝弱密钥、开发默认值、示例占位值、mock SiliconFlow、mock 本站短信和演示数据初始化。
- 本站短信在开发模式可用固定演示码；生产环境未接入真实服务时统一返回 503，不会回退到固定验证码。
- SiliconFlow 登录已建立独立 broker、数据表、配置和 API 失败关闭边界；真实 Chromium/viewer 网关未配置时返回 503 且不写入会话。
- 已修复退款/关闭订单可被客户接口重新激活、退款后超时记录仍可获奖、已锁奖励可被无效审核降级三个状态漏洞。
- 生产配置新增 `MVP_ALLOWED_HOSTS` 和 Trusted Host 中间件；生产必须显式声明域名，未知 Host 返回 400。
- `deploy/` 已提供 Ubuntu 安装、systemd、Nginx HTTP/HTTPS、Let's Encrypt、显式 UFW、健康检查和生产启动烟雾测试。
- `deploy/wsl/` 已提供 Cloudflare Quick Tunnel 安装和临时公网启动脚本；不依赖自有域名、云服务器或 Cloudflare 账号，每轮使用临时数据库、随机凭据、精确 Host 白名单和 Secure Cookie。
- SQLite 备份使用 backup API 创建一致性副本并执行 `integrity_check`；systemd timer 每日运行，默认保留 7 天。

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
10. **生产配置失败关闭**：所有安全相关运行模式由集中配置校验；正式环境缺少强密钥或仍使用任何演示能力时在导入/启动阶段直接失败。真实短信未接通时宁可禁止登录，也不接受固定验证码。
11. **用户声明不等于平台核验**：抢单人提交的 SiliconFlow 用户 ID 独立存储为 `PENDING` 声明，不改变 assignment 注册/认证状态；只有管理员或未来受信同步器才能锁定奖励。
12. **远程浏览器独立编排**：异步真人接力不复用同步 SiliconFlow adapter，也不得在 SQLite 写事务内启动浏览器。当前 broker 只实现 `disabled`，避免未配置网关时误启用。
13. **淘宝第一阶段采用人工运营**：淘宝只作为付款和聊天渠道；运营人员核对付款后在本站建单并人工发送客户链接。生产 webhook、订单查询和自动聊天不在当前开发范围内。
14. **测试部署采用单进程单机**：Uvicorn 仅监听 `127.0.0.1`，Nginx 是唯一公网入口；SQLite 阶段禁止多 worker。HTTP 只用于 ACME，证书成功后才代理应用。
15. **防火墙必须显式启用**：安装脚本不会自动开启 UFW，避免错误 SSH 端口导致失联；运营人员必须传入实际 SSH 端口执行独立脚本。
16. **先临时联调、后购买资源**：WSL Quick Tunnel 只用于合成数据和人工监督下的短时测试，退出即删除数据库并失效；它不能替代固定域名、7x24 服务器、备份、监控或生产安全能力。

## 核心文件

| 文件 | 作用 |
|---|---|
| `mvp_app/main.py` | FastAPI 路由、认证、订单、抢单、奖励、人工支付、Taobao mock/webhook 安全开关 |
| `mvp_app/config.py` | 环境变量集中解析、开发/生产默认值和生产启动安全校验 |
| `mvp_app/browser_handoff.py` | 手机真人浏览器接力 broker 边界；当前仅提供失败关闭实现 |
| `mvp_app/database.py` | SQLite schema、事务连接、提醒/过期扫描、容量统计、演示数据 |
| `mvp_app/adapters.py` | SKU 映射、邀请码校验、SiliconFlow mock/manual/live-disabled 适配器 |
| `mvp_app/security.py` | HMAC、AES-GCM、站内会话签名、数据掩码 |
| `static/index.html` | 单页应用外壳和登录/支付宝对话框 |
| `static/app.js` | 客户、抢单人和管理员端交互 |
| `static/styles.css` | 桌面/移动响应式样式 |
| `deploy/` | Ubuntu 安装、Nginx/HTTPS、systemd、UFW、健康检查、生产烟雾测试、SQLite 备份和 WSL 临时公网联调 |
| `deploy/wsl/` | cloudflared 官方仓库安装、临时公网编排和全流程公网自测 |
| `tests/conftest.py` / `tests/test_mvp.py` / `tests/test_config.py` / `tests/test_deployment.py` | 56 项配置、API、权限、并发、安全、部署和生命周期测试 |
| `run.ps1` / `run-tests.ps1` | 本地启动和复验入口 |
| `run.sh` / `run-tests.sh` / `smoke-test.sh` | Linux/macOS 启动、测试和服务健康检查入口 |
| `requirements.txt` / `requirements-dev.txt` / `.env.example` / `.env.production.example` | 运行依赖、开发测试依赖和非敏感配置模板 |
| `README.md` / `MVP-STAGE-REPORT.md` | 使用说明和阶段验收结论 |
| `USER_GUIDE.md` | 管理员、客户和抢单人的当前 MVP 操作手册及生产边界 |
| `REMOTE_BROWSER_GATEWAY.md` | 手机真人浏览器接力的状态机、接口、安全边界和启用门槛 |
| `../tech-validation/validation-report.md` | 外部协议、风险和 Go/No-Go 总结 |
| `../README.md` / `../DEPENDENCIES.md` | GitHub 仓库入口和依赖边界 |
| `../CONTRIBUTING.md` / `../SECURITY.md` | 协作流程和安全要求 |
| `../.github/workflows/ci.yml` | Python 3.12/3.13 的 GitHub CI |

生成文件 `data/mvp.db`、`.pytest_cache/` 和 `__pycache__/` 不属于源代码，建立 Git 仓库时应忽略。

## 测试与验证结果

2026-08-18 在当前工作区重新执行：

```powershell
cd outputs\mvp
powershell -ExecutionPolicy Bypass -File .\run-tests.ps1
```

Windows PowerShell 最新结果：`56 passed in 9.96s`，无测试警告。覆盖：

- mock 代理登录、会话密文检查、邀请码返回、抢单、认证、奖励和支付完整闭环；
- SKU 1/5/10 映射；登录和支付宝前置条件；
- N=1/5/10 实际 API 并发不超额及重复抢单幂等；
- 超时补做有空位获奖、不得侵占活跃保护位、24 小时截止；
- 15 分钟提醒幂等、过期会话删除；
- 淘宝 mock 付款幂等、退款关闭、真实 webhook 失败关闭；
- SiliconFlow 真实适配器失败关闭；
- 开发/生产配置解析、生产弱值和占位值拒绝、mock/演示能力拒绝、本站短信禁用失败关闭。
- 公开邀请码隔离、抢单本人 ID 密文声明、跨用户对象权限、管理员复核一致性；
- 退款订单不可复活或新增奖励、已锁奖励不可被降级、远程浏览器禁用零副作用。
- 可信 Host、systemd/Nginx 部署约束、生产失败关闭模式和 SQLite 备份完整性。

同日执行 `../tech-validation/run-validation.ps1`：

- 只读端点模式：23 个；未触发 SMS、OTP、CAPTCHA、订单或支付动作；
- 业务规则：5/5；
- 并发模型：6/6；
- 合成会话安全：8/8；
- Markdown/JSON 敏感输出扫描：13 个文件通过。

2026-08-18 在 WSL2 Ubuntu 24.04.1 上重新执行原生 Linux 复验：

- Linux Python 3.12.3，虚拟环境解释器解析到 `/usr/bin/python3.12`；
- `./run-tests.sh`：`56 passed in 11.80s`；
- `deploy/production-smoke-test.sh`：生产模式启动成功，`manual/disabled/disabled` 失败关闭组合正确，未知 Host 返回 400；
- `deploy/validate-assets.sh`：systemd 单元和 Nginx 1.24 HTTP/HTTPS 模板解析通过；
- `./smoke-test.sh`：Uvicorn 启动成功，`/api/health` 返回 200，并明确报告 `site_sms_mode=mock`、`remote_browser_mode=disabled`；
- PowerShell 7.6.5 下完整技术验证通过：只读端点 23、业务规则 5/5、并发 6/6、会话安全 8/8、敏感输出扫描通过；
- Linux 虚拟环境 `pip check` 无依赖冲突，`pip-audit` 未发现已知漏洞。

同日完成 WSL 临时公网现场验证：安装 `cloudflared 2026.8.2`，通过随机 `trycloudflare.com` HTTPS 地址从公网访问健康检查，并自动走完“管理员建单 -> 客户 mock 登录/邀请码 -> 抢单人本站登录/支付宝登记 -> 抢单 -> mock 注册认证 -> 人工支付登记”的完整闭环，最终奖励状态为 `PAID`。临时地址、随机凭据、数据库和日志在测试结束后均已销毁；该结果只证明公网页面与 mock 业务链路，不代表真实短信或真实 SiliconFlow 已通过。

本次浏览器验收覆盖 390×844 手机和 1440×900 桌面：未抢单邀请码不可见，登录/支付宝/抢单后官方链接出现，用户 ID 提交后只显示掩码和待核验；按钮最小高度 44px，无横向溢出，控制台 0 个错误/警告。本地服务运行于 `http://127.0.0.1:8765`。

## Git 状态

仓库根目录为 `outputs/`，包含应用与技术验证包。已在该目录初始化 `main` 分支，并添加 `.gitignore`、`.gitattributes`、`.editorconfig`、依赖说明、贡献指南、安全说明、PR 模板和 GitHub CI。GitHub 公开仓库为 `longtongzhao-cloud/siliconflow-invite-task-mvp`，首个基线提交和推送于 2026-08-16 完成。

2026-08-17 完成生产配置失败关闭：新增集中配置、生产配置模板、启动级占位值拒绝、本站短信禁用保护及对应测试；Windows 和 WSL 均已复验。

2026-08-18 完成测试部署代码准备：新增可信 Host、Ubuntu/systemd/Nginx/Let's Encrypt/UFW 脚本、生产烟雾测试、SQLite 一致性备份与 CI 覆盖。尚未在真实云服务器和域名执行。

2026-08-18 完成免购买资源的 WSL 临时公网方案：新增 Cloudflare Quick Tunnel 安装/编排脚本、Secure Cookie 显式配置、临时数据清理和公网全流程自测；实际公网 mock 闭环已通过。

`git add --dry-run .` 已确认候选列表只包含源码、测试、文档和仓库配置；`mvp/.venv/`、`mvp/data/mvp.db`、缓存和 `tech-validation/evidence/*.json` 均被忽略。

仓库整理时使用 `pip-audit` 发现旧版 `cryptography`、`pytest` 和 FastAPI 间接依赖 Starlette 存在已知漏洞，因此已升级并显式固定安全版本。升级后 `pip check` 返回 `No broken requirements found`，`pip-audit` 返回 `No known vulnerabilities found`；GitHub CI 会继续执行依赖漏洞审计。

应用代码没有 Windows 专用运行时依赖。仓库已补充 Bash 入口，技术验证脚本已消除对子进程命令 `powershell` 的硬编码，GitHub CI 覆盖 Ubuntu/Windows 与 Python 3.12/3.13。WSL2 Ubuntu 24.04.1 已完成原生复验；共享工作区使用独立 Linux 虚拟环境，避免误用 Windows `.venv`。

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
- 第一版已经确定长期先人工创建订单并发送客户链接；淘宝 API 与聊天自动发送延期。代码仅实现全额退款/关闭，人工录错或部分退款仍需运营流程处理。

### 部署、账号与运营

- 尚无自有公网域名和云服务器；DNS、真实 Let's Encrypt、云安全组和稳定公网 HTTPS 尚未现场通过。WSL 临时公网 HTTPS 已通过，但 URL 每次启动变化，依赖本机开机、网络和前台脚本，不能用于 7x24 服务。
- systemd/Nginx/UFW 和 SQLite 备份代码已准备并在 WSL 解析验证，但尚未完成真实服务器安装、跨机备份、恢复演练和监控告警。
- 仍无 KMS、管理员 MFA/RBAC 和生产 PostgreSQL；当前部署仅允许单进程 SQLite 测试环境。
- 候选域名未购买；`gjlt.com` 已被注册，其他候选在购买前必须重新查询实时状态和商标/混淆风险。
- 本站真实短信仍未接通。固定演示验证码只允许开发模式；生产模式已失败关闭。普通阿里云短信签名需要企业资质；个人主体可评估阿里云号码认证服务的“短信认证”产品。
- SiliconFlow 登录真实网关尚未实现：缺 Chromium 容器编排、一次性 viewer、WebRTC/noVNC、5 分钟销毁、断线重连和受信结果回调；`MVP_REMOTE_BROWSER_MODE` 必须保持 `disabled`。
- 支付宝仅登记收款信息，未验证账户归属；尚未执行真实 5 元转账或对账。
- 生产配置启动校验和 Secure Cookie 已实现，但管理员仍只有单一静态密钥，没有 MFA/RBAC；密钥也尚未接入 KMS，不能直接公网运营。

## 尝试过但未形成可用方案

1. **匿名手机号直接查询邀请码**：参考站实际是验证码后代理登录，不是匿名查询；该假设已排除。
2. **直接复刻 SiliconFlow 网页接口作为开放 API**：能看到登录端点和前端字段，但存在易盾、设备令牌、私有契约和授权/稳定性缺口；未实现 live 调用。
3. **通过标准 OAuth/OIDC 获取 SiliconFlow 邀请数据**：公开 discovery 和 API Reference 未发现邀请/认证 scope 或端点。
4. **用淘宝个人开发者认证直接取得订单权限**：当前应用软件开发商及自研商家指南要求企业身份/资料，尚未得到 `trade.fullinfo.get` 或消息订阅权限。
5. **自动通过淘宝聊天发送动态外链**：未发现当前账号已有专项能力，MVP 保留人工复制发送。
6. **本地电脑承接生产回调**：Quick Tunnel 已证明可以开发和受监督联调，但没有固定地址或 SLA，不能作为 7x24 淘宝 webhook 和客户访问方案。
7. **普通阿里云短信自用签名**：个人主体无法完成当前运营商实名报备；应改用免企业资质的短信认证产品或后续企业资质。

## 下一步开发顺序

1. **配置 GitHub 协作保护**：仓库已经公开；下一步确定许可证和对外披露范围，为 `main` 启用 PR、CI 和至少一名审查者要求，启用私密漏洞报告，并邀请实际协作者。
2. **WSL 手机端受控验收**：按 `deploy/wsl/README.md` 启动临时 HTTPS，只用合成数据，让管理员、客户和抢单人分别用手机完成 mock 流程并记录页面/操作问题；每轮结束关闭隧道并确认临时数据已删除。
3. **接入本站真实短信**：优先验证阿里云号码认证服务的短信认证；将固定演示验证码替换为发送/核验 API、限流和回执处理。
4. **手机真人接力网关**：临时 HTTPS 已不再是界面联调阻塞；下一步实现隔离 Chromium、一次性 viewer、5 分钟空闲销毁、断线重连、受信回调验签和清理重试。账号本人解决 CAPTCHA 并输入 OTP，禁止验证码/令牌日志；取得 SiliconFlow 许可前保持失败关闭。
5. **决定固定基础设施**：手机端流程通过且需要固定地址/持续在线后，再查询并购买中性域名与预算内 Ubuntu 服务器，按 `deploy/README.md` 完成 DNS、UFW、Let's Encrypt、健康检查、跨机备份和恢复演练。
6. **生产化基础设施**：将 SQLite 迁移 PostgreSQL，引入 schema migration、KMS/密钥轮换、管理员 MFA/RBAC、审计、备份恢复、错误监控和一键冻结开关。
6. **真人三阶段验收**：使用一个全新用户依次验证注册前、注册未实名、首次有效实名；人工对照官方邀请记录，测量状态延迟。无法获得重复/无效样本时保持人工判奖。
7. **支付与争议闭环**：执行一笔受控 5 元人工转账，验证流水幂等、支付失败不释放容量、隐私遮罩、对账和申诉处理。
8. **人工订单运营验收**：验证付款核对、重复订单号拦截、错单关闭、链接错发处置、退款处理和操作审计；淘宝 API 仅作为未来可选增强项。
9. **上线门复测**：重跑全部 P0 并发、安全、删除、外部失败和浏览器测试；真实写接口、真实支付与用户数据测试必须单独留存脱敏证据。

## 继续工作的入口

- 本地启动：`powershell -ExecutionPolicy Bypass -File .\run.ps1`
- MVP 测试：`powershell -ExecutionPolicy Bypass -File .\run-tests.ps1`
- Linux/macOS 启动：`./run.sh`
- Linux/macOS 测试：`./run-tests.sh`
- 技术验证：在 `../tech-validation/` 执行 `powershell -ExecutionPolicy Bypass -File .\run-validation.ps1`
- 阶段结论：`MVP-STAGE-REPORT.md`
- 当前版本使用说明：`USER_GUIDE.md`
- WSL 临时公网测试：`deploy/wsl/README.md`
- Ubuntu 固定服务器部署：`deploy/README.md`
- 外部接口与风险总览：`../tech-validation/validation-report.md`
- 真人现场步骤：`../tech-validation/live-test-runbook.md`

所有真实 AppSecret、Access Token、OTP、会话令牌和支付凭据只能通过部署环境的密钥管理配置，不得写入仓库、交接文档、日志或聊天。
