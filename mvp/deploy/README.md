# Ubuntu 测试部署

本目录把当前 MVP 部署为单机 Ubuntu 服务。它适合受控测试，不代表生产上线完成。

购买域名和服务器前，先按 `wsl/README.md` 使用临时公网 HTTPS 完成手机端 mock 联调。本页描述需要固定域名和持续在线后的单机服务器部署。

## 部署边界

- Uvicorn 只监听 `127.0.0.1:8765`，公网流量必须经过 Nginx。
- 应用运行在独立的 `siliconflow-mvp` 系统用户下；环境文件权限为 `0640`。
- 生产配置必须声明 `MVP_ALLOWED_HOSTS`，未知 Host 会被应用拒绝。
- SQLite 数据位于 `/var/lib/siliconflow-invite-task/mvp.db`，只运行一个应用进程。
- 每天创建一次 SQLite 在线一致性备份，默认保留 7 天；备份位于 `/var/backups/siliconflow-invite-task/`。
- 安装脚本默认短信为 `disabled`、SiliconFlow 为 `manual`、远程浏览器为 `disabled`。阿里云短信适配器虽已实现，仍须按 `../ALIYUN_SMS_SETUP.md` 完成账号开通和受控真发后再修改环境文件；真实 SiliconFlow 代理登录仍不可用。
- 安装脚本不会自动启用 UFW，也不会在 DNS 未解析时申请证书。
- 证书启用前，Nginx 的 HTTP 配置只响应 ACME 验证，其余请求返回 503；不要通过 HTTP 使用管理台或传输客户数据。

## 服务器技术下限

当前单进程 SQLite 测试环境建议至少 1 vCPU、2 GB 内存、20 GB 系统盘和一个公网 IPv4。服务器应运行 Ubuntu 24.04 LTS，并允许入站 TCP 22（或实际 SSH 端口）、80 和 443。不要把本地 Windows/WSL 电脑作为长期公网服务器。

## 执行顺序

1. 购买一个中性域名和 Ubuntu 服务器。
2. 在 DNS 中为测试域名创建 A 记录，指向服务器公网 IPv4。
3. 在服务器克隆仓库，进入 `mvp` 目录。
4. 先安装仅用于 ACME 的 HTTP 引导服务：

```bash
sudo ./deploy/ubuntu/install.sh --domain tasks.example.com
```

首次安装会生成随机 `MVP_SECRET` 和 `MVP_ADMIN_KEY`，只写入 `/etc/siliconflow-invite-task/mvp.env`，不会打印到终端。重复安装会创建新 release 并保留原环境文件和数据库。

5. 确认实际 SSH 端口后，再显式配置防火墙：

```bash
sudo ./deploy/ubuntu/configure-firewall.sh --ssh-port 22
```

6. 等待公网 DNS 生效，然后申请 Let's Encrypt 证书并切换 HTTPS：

```bash
sudo ./deploy/ubuntu/enable-tls.sh tasks.example.com admin@example.com
```

7. 执行部署检查：

```bash
sudo ./deploy/ubuntu/verify.sh tasks.example.com
```

开发机或 CI 可先检查 Bash、systemd 和已安装的 Nginx 模板：

```bash
sudo ./deploy/validate-assets.sh
```

隔离验证生产配置启动、健康检查和 Host 拒绝策略：

```bash
bash ./deploy/production-smoke-test.sh
```

## 运维命令

```bash
sudo systemctl status siliconflow-invite-task
sudo journalctl -u siliconflow-invite-task -n 100 --no-pager
sudo systemctl status siliconflow-invite-task-backup.timer
sudo systemctl start siliconflow-invite-task-backup.service
sudo nginx -t
```

查看管理员密钥时必须在私密终端操作，不要截图或发送到聊天：

```bash
sudo sed -n 's/^MVP_ADMIN_KEY=//p' /etc/siliconflow-invite-task/mvp.env
```

## 更新与回滚

拉取新提交后，再次运行 `install.sh` 会创建 `/opt/siliconflow-invite-task/releases/<UTC时间>/` 并原子切换 `current` 符号链接。更新前后都应执行 `verify.sh`。

回滚时先列出 releases，选择已验证的旧目录，再原子切换并重启：

```bash
sudo ls -1 /opt/siliconflow-invite-task/releases
sudo ln -sfn /opt/siliconflow-invite-task/releases/<旧版本> /opt/siliconflow-invite-task/current.next
sudo mv -Tf /opt/siliconflow-invite-task/current.next /opt/siliconflow-invite-task/current
sudo systemctl restart siliconflow-invite-task
sudo ./deploy/ubuntu/verify.sh tasks.example.com
```

不要通过复制正在运行的 `mvp.db` 文件制作备份。应启动 `siliconflow-invite-task-backup.service`，它使用 SQLite backup API 并执行 `integrity_check`。

## 恢复演练

恢复会覆盖当前数据库，只能在维护窗口由管理员显式执行。先列出备份并选择一个已经同步到异机存储的副本：

```bash
sudo ls -lh /var/backups/siliconflow-invite-task/
sudo ./deploy/ubuntu/restore-backup.sh --confirm \
  /var/backups/siliconflow-invite-task/mvp-<timestamp>.db
```

恢复脚本会先为当前状态再创建一份一致性备份，校验选定文件，停止应用，清理旧 WAL/SHM，恢复后重新启动并检查健康状态。数据库中的加密字段依赖原 `MVP_SECRET`；环境文件或未来 KMS 密钥必须通过独立的加密渠道备份，不能与数据库副本存放在同一位置。
