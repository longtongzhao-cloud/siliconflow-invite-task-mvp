# 依赖说明

最后核对日期：2026-08-16

## Python

项目代码基线为 Python 3.11 及以上。当前本地验证环境是 Windows/Python 3.13.9；GitHub CI 同时覆盖 Ubuntu 和 Windows 的 Python 3.12、3.13。

运行依赖位于 `mvp/requirements.txt`：

| 依赖 | 用途 |
|---|---|
| `fastapi` | HTTP API、路由和请求校验 |
| `starlette` | FastAPI 的 ASGI 基础；显式固定已审计版本 |
| `uvicorn` | 本地 ASGI 服务 |
| `cryptography` | AES-256-GCM 字段加密 |

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

完整验证中的只读探针会访问参考站点，因此可能受网络、站点状态或对方页面变更影响。GitHub CI 只运行确定性的本地规则、并发、会话安全和敏感输出检查，不运行外部网络探针。Ubuntu CI 还会对 Bash 脚本做语法检查，并启动服务验证 `/api/health`。

## 升级规则

1. 在独立分支修改版本，不直接更新 `main`。
2. 查阅依赖的官方发布说明和安全公告。
3. 执行 `python -m pip check`、MVP 全部测试和本地技术验证。
4. 使用 `pip-audit -r mvp/requirements-dev.txt` 检查已知漏洞。
5. 在 PR 中记录升级原因、行为变化和回滚方式。
6. 不提交本机 `pip freeze` 的全部间接依赖，除非项目正式引入跨平台锁文件工具。
