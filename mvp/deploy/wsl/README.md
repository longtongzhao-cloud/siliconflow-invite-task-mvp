# WSL 临时公网测试

此流程使用 Cloudflare Quick Tunnel 为 WSL 中的本地应用生成临时 `https://*.trycloudflare.com` 地址，不需要购买域名、云服务器或配置入站端口。

## 能验证什么

- 淘宝人工建单、复制客户链接；
- 客户和抢单人在不同手机网络打开页面；
- mock SiliconFlow 登录、邀请码、抢单、人工核验和奖励状态机；
- 显式配置后，仅对白名单测试手机号验证阿里云本站短信发送和核验；
- HTTPS 下的 Secure Cookie、可信 Host 和移动端页面。

默认 mock 流程不能验证真实短信；即使启用阿里云本站短信，它仍不能验证真实 SiliconFlow 会话/认证状态、长期运行、固定域名、云防火墙或服务器重启恢复。

## 安全边界

- Quick Tunnel 是公开互联网地址，不是内网共享。
- 默认 mock 模式只允许合成手机号、支付宝资料、订单号和 SiliconFlow ID。
- `aliyun-dypns` 模式只允许白名单测试手机号及其本站 OTP 为真实值；支付宝、订单、SiliconFlow ID 和支付流水仍必须为合成数据。
- 不得输入真实 SiliconFlow OTP/Cookie、支付宝资料、身份证或其他生产数据。
- 每次启动使用新的随机 URL、密钥和临时数据库；按 `Ctrl+C` 后全部删除。
- URL 无访问控制。脚本要求显式传入 `--accept-public-demo-risk`，避免误启动。
- 电脑休眠、关机、网络断开或脚本退出后，地址立即不可用。

Cloudflare 官方将 Quick Tunnel 定位为开发测试功能：随机域名、无 SLA、最多 200 个并发请求、不支持 SSE。不要把此流程用于对外经营。

官方说明：[Cloudflare Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/)；[cloudflared 安装](https://developers.cloudflare.com/tunnel/downloads/)。

## 安装

在 WSL Ubuntu 中进入 `mvp` 目录，按 Cloudflare 官方签名 APT 仓库安装：

```bash
sudo ./deploy/wsl/install-cloudflared.sh
```

## 启动

```bash
./deploy/wsl/start-quick-tunnel.sh --accept-public-demo-risk
```

脚本就绪后会显示临时 HTTPS 地址、随机管理员密钥和本轮演示验证码。保持终端开启，用手机访问该地址；结束时按 `Ctrl+C`。

自动化或短时验证可设置持续秒数：

```bash
./deploy/wsl/start-quick-tunnel.sh --accept-public-demo-risk --duration 20
```

经公网自动走完“建单 -> 客户邀请码 -> 抢单人登录/支付宝 -> 抢单 -> mock 认证 -> 奖励登记”闭环：

```bash
./deploy/wsl/start-quick-tunnel.sh \
  --accept-public-demo-risk --self-test-flow --duration 5
```

真实本站短信验收不会自动运行，必须先完成 `../../ALIYUN_SMS_SETUP.md` 的账号侧步骤，并在私密 WSL 终端执行其中的限时启动命令。脚本要求 `--accept-real-sms-cost`、1 到 3600 秒时长和白名单手机号，且硬限制 5 条/小时、10 条/日。

若 `~/.cloudflared/config.yml` 或 `config.yaml` 已存在，脚本会使用独立的空配置文件，不读取或修改现有 Tunnel 配置。
