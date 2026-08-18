# 依赖说明

最后核对日期：2026-08-18

## Python

项目代码基线为 Python 3.11 及以上。当前本地验证环境是 Windows/Python 3.13.9；GitHub CI 同时覆盖 Ubuntu 和 Windows 的 Python 3.12、3.13。

Ubuntu/WSL 需要安装 `python3-venv`：`sudo apt-get install python3-venv`。WSL 共享 Windows 工作区时，Bash 脚本会使用 Linux 用户缓存目录中的独立虚拟环境；不要尝试共用 Windows 创建的 `.venv`。

运行依赖位于 `mvp/requirements.txt`：

| 依赖 | 用途 |
|---|---|
| `fastapi` | HTTP API、路由和请求校验 |
| `starlette` | FastAPI 的 ASGI 基础；显式固定已审计版本 |
| `uvicorn` | 本地 ASGI 服务 |
| `cryptography` | AES-256-GCM 字段加密 |
| `alibabacloud-dypnsapi20170525` | 阿里云号码认证服务短信发送与核验官方 SDK；仅 `aliyun-dypns` 模式发起外部调用 |

开发与测试依赖位于 `mvp/requirements-dev.txt`：

| 依赖 | 用途 |
|---|---|
| `httpx2` | FastAPI/Starlette `TestClient` 的 HTTP 客户端依赖 |
| `pytest` | API、并发、安全和生命周期测试 |

所有直接依赖使用精确版本；Starlette 作为安全敏感的间接依赖也显式固定。安装运行依赖：

```powershell
python -m pip install -r .\mvp\requirements.txt
```

安装开发依赖：

```powershell
python -m pip install -r .\mvp\requirements-dev.txt
python -m pip check
```

## 前端

前端为原生 HTML、CSS 和 JavaScript，没有 Node.js、npm 或前端构建步骤。

## 验证工具

`tech-validation/` 在 Windows 可使用 Windows PowerShell 5.1 或 PowerShell 7，在 Linux 需要 PowerShell 7 (`pwsh`)。会话安全脚本还需要 Python 和 `cryptography`。并发验证使用 PowerShell/C# 本地编译能力，不需要单独的项目包。

Ubuntu 的 PowerShell 7 应按 [Microsoft 官方安装说明](https://learn.microsoft.com/powershell/scripting/install/install-ubuntu) 从 Microsoft Package Repository 安装。

## 测试部署

Ubuntu 单机部署脚本使用系统包：`ca-certificates`、`curl`、`nginx`、`openssl`、`python3`、`python3-venv`、`rsync`、`ufw` 和 `certbot`。应用不依赖 Docker。Nginx 只代理到本机 `127.0.0.1:8765`，证书通过 Certbot webroot 模式申请。

WSL 临时公网联调额外使用 Cloudflare 官方签名 APT 仓库中的 `cloudflared`。它只服务于短时 Quick Tunnel 测试，不是应用运行依赖，也不进入 Python 依赖文件；安装和清理边界见 `mvp/deploy/wsl/README.md`。

`mvp/deploy/validate-assets.sh` 会检查 Bash，在已安装 ShellCheck 时执行静态分析，并验证 systemd；已安装 Nginx/openssl 时还会解析 HTTP 和 HTTPS 模板。`mvp/deploy/production-smoke-test.sh` 使用临时数据库与测试专用密钥启动生产配置，不接触真实外部平台。

真实本站短信使用阿里云 PNVS 出站 API，不要求短信回调地址。SDK 已固定版本；没有完整环境变量与测试手机号白名单时应用会在启动或调用前失败关闭，测试套件使用假客户端，不发送短信。

完整验证中的只读探针会访问参考站点，因此可能受网络、站点状态或对方页面变更影响。GitHub CI 只运行确定性的本地规则、并发、会话安全和敏感输出检查，不运行外部网络探针。Ubuntu CI 还会验证 Bash/systemd 部署资产，并分别以开发和生产失败关闭配置启动服务验证 `/api/health`。

## 升级规则

1. 在独立分支修改版本，不直接更新 `main`。
2. 查阅依赖的官方发布说明和安全公告。
3. 执行 `python -m pip check`、MVP 全部测试和本地技术验证。
4. 使用 `pip-audit -r mvp/requirements-dev.txt` 检查已知漏洞。
5. 在 PR 中记录升级原因、行为变化和回滚方式。
6. 不提交本机 `pip freeze` 的全部间接依赖，除非项目正式引入跨平台锁文件工具。
