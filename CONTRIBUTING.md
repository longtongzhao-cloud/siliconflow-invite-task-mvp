# 贡献指南

## 开始开发

1. 从 `main` 创建短生命周期分支，例如 `feature/taobao-adapter`、`fix/reward-capacity` 或 `docs/user-guide`。
2. 在 `mvp/` 中运行 `run-tests.ps1`，确认基线通过。
3. 只修改当前需求涉及的模块；外部平台适配器与核心订单状态机保持隔离。
4. 为行为变化增加测试，并同步更新 `mvp/PROJECT_STATUS.md` 或相关使用文档。
5. 发起 PR 前完成下述检查。

```powershell
cd .\mvp
powershell -ExecutionPolicy Bypass -File .\run-tests.ps1
python -m pip_audit -r .\requirements-dev.txt

cd ..\tech-validation
powershell -ExecutionPolicy Bypass -File .\test-task-rules.ps1
powershell -ExecutionPolicy Bypass -File .\test-task-concurrency.ps1
python .\test-session-security.py
powershell -ExecutionPolicy Bypass -File .\test-sensitive-output.ps1
```

完整 `run-validation.ps1` 还包含外部只读探针，应在需要重新核对参考站时单独运行，不作为普通代码 PR 的稳定前置条件。

## 代码和数据要求

- Python 代码保持现有类型标注和模块边界，避免把第三方网页字段扩散到业务层。
- 时间、名额和奖励结算以服务端数据库事务为准，前端状态不能作为判奖依据。
- 新增外部调用必须设置超时、错误映射、失败关闭、审计和人工回退。
- 不采集身份证、人脸或证件图片；新增个人信息字段前必须说明目的、保存期限和删除机制。
- 数据库 schema 变化必须附迁移方案；在正式引入迁移工具前，不直接修改已有生产数据。
- 不提交真实手机号、OTP、会话令牌、API 凭据、支付宝资料、数据库或未脱敏截图。

## 提交与 PR

建议使用清晰的提交前缀：`feat:`、`fix:`、`test:`、`docs:`、`refactor:`、`chore:`。

每个 PR 应说明：

- 解决的问题和范围；
- 关键设计与风险；
- 已运行的测试及结果；
- 配置、schema、隐私或外部权限变化；
- 无法验证的部分和回滚方式。

至少一名未参与实现的协作者完成审查后再合并。涉及奖励容量、支付、身份去重、加密或 live 外部调用时，应增加针对并发和失败路径的测试。

## 分支保护建议

GitHub 仓库创建后，为 `main` 启用：

- 禁止直接推送；
- 合并前必须通过 PR；
- 必须通过 `test` CI；
- 至少一名审查者批准；
- 合并前分支必须为最新状态；
- 禁止强制推送和删除分支保护规则。
