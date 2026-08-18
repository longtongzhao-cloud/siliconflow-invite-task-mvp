# SiliconFlow 邀新任务台

这是一个处于本地 MVP 阶段的邀新任务系统，覆盖订单建单、客户邀请码配置、N 人抢单限额、30 分钟保护、24 小时订单截止、人工核验和 5 元人工奖励登记。

当前仓库不能直接用于生产：SiliconFlow 真实代理登录、淘宝订单/消息权限、本站真实短信和支付宝自动付款均未接通。开发环境使用不联网的 mock 或人工适配器。

## 仓库结构

```text
.
|-- mvp/                    # FastAPI 应用、静态前端、测试、部署和使用文档
|-- tech-validation/        # 只读协议探针、业务规则和安全验证
|-- .github/                # GitHub Actions 与 PR 模板
|-- CONTRIBUTING.md         # 协作流程和提交要求
|-- DEPENDENCIES.md         # Python 及工具依赖说明
`-- SECURITY.md             # 安全边界和漏洞报告要求
```

运行数据、虚拟环境、缓存、日志、环境变量文件和生成的验证证据均由 `.gitignore` 排除。

## 快速开始

Windows PowerShell：

```powershell
cd .\mvp
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

打开 <http://127.0.0.1:8765>。首次运行会在 `mvp/.venv` 创建虚拟环境并安装运行依赖。

Linux/macOS Bash：

```bash
cd ./mvp
./run.sh
```

Linux 修改监听地址或端口时使用环境变量，例如 `MVP_HOST=0.0.0.0 MVP_PORT=8766 ./run.sh`。

在 WSL 中直接运行 Windows 挂载目录里的项目时，脚本会自动把 Linux 虚拟环境放到 `~/.cache/siliconflow-invite-task-mvp/venv`，避免误用 Windows 的 `mvp/.venv`。可通过 `MVP_VENV_PATH` 自定义位置。

运行应用测试：

```powershell
cd .\mvp
powershell -ExecutionPolicy Bypass -File .\run-tests.ps1
```

Linux/macOS：

```bash
cd ./mvp
./run-tests.sh
```

Linux 服务启动冒烟测试：`./mvp/smoke-test.sh`。

购买域名和服务器前，可用 WSL + Cloudflare Quick Tunnel 获得临时公网 HTTPS 地址并从手机联调，见 [WSL 临时公网测试](mvp/deploy/wsl/README.md)。固定域名的 Ubuntu 单机部署资产位于 `mvp/deploy/`，完整流程见 [Ubuntu 测试部署](mvp/deploy/README.md)。

运行完整技术验证：

```powershell
cd .\tech-validation
powershell -ExecutionPolicy Bypass -File .\run-validation.ps1
```

Linux 需要 PowerShell 7，然后执行：

```bash
cd ./tech-validation
./run-validation.sh
```

完整操作流程见 [MVP 使用说明](mvp/USER_GUIDE.md)，当前状态和后续顺序见 [项目交接文档](mvp/PROJECT_STATUS.md)。

## 协作前必读

- 阅读 [贡献指南](CONTRIBUTING.md) 和 [安全说明](SECURITY.md)。
- 不要提交 `.env`、数据库、手机号、OTP、Cookie、Access Token、支付凭据或真实用户证据。
- 外部平台 live 调用必须使用独立适配器、明确开关和受监督测试，不得把私有网页接口直接写进核心状态机。
- 当前仓库尚未选择开源许可证。在确定许可证前，公开可见不等于授权他人复制、分发或商用。

## GitHub 仓库

公开仓库：<https://github.com/longtongzhao-cloud/siliconflow-invite-task-mvp>

首次克隆：

```powershell
git clone https://github.com/longtongzhao-cloud/siliconflow-invite-task-mvp.git
cd siliconflow-invite-task-mvp
```

仓库所有者需要在 GitHub 的 Collaborators 设置中邀请协作者。每次提交前必须检查 `git status`，确认数据库、`.env`、虚拟环境和生成证据没有进入待提交列表。
