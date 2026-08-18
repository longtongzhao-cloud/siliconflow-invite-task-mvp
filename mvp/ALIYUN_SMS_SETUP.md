# 阿里云短信认证接入与验收

最后核对日期：2026-08-18

本站接入的是阿里云号码认证服务（PNVS）的“短信认证”，不是传统短信服务。该产品支持个人实名认证开发者使用系统赠送签名和模板，通过 `SendSmsVerifyCode` 发送、`CheckSmsVerifyCode` 核验，适用于 Web/H5。

按 2026-08-18 官方价格页，月发送量不超过 1000 条时按量价格为 0.06 元/成功发送，核验免费；1000 条套餐为 54 元。价格可能调整，真发前以控制台和官方价格页为准。

官方入口：

- [个人开发者接入指南](https://help.aliyun.com/zh/pnvs/use-cases/sms-verify-for-individual-developers)
- [短信认证新手指引](https://help.aliyun.com/zh/pnvs/getting-started/sms-authentication-service-novice-guide)
- [发送验证码 API](https://help.aliyun.com/zh/pnvs/developer-reference/api-dypnsapi-2017-05-25-sendsmsverifycode)
- [核验验证码 API](https://help.aliyun.com/zh/pnvs/developer-reference/api-dypnsapi-2017-05-25-checksmsverifycode)
- [官方价格](https://help.aliyun.com/zh/pnvs/product-overview/product-pricing/)

## 账号侧前置步骤

以下操作必须由阿里云账号持有人在控制台完成，代码无法代办：

1. 完成阿里云个人实名认证。
2. 进入号码认证服务控制台，开通“短信认证”，确认账户余额或按量付费状态。
3. 在快速测试中绑定本人的测试手机号。快速测试最多绑定 5 个号码；这是测试区限制，不是正式 API 的永久发送范围。
4. 选择系统赠送签名和系统赠送登录/注册模板，记录控制台显示的 `SignName` 和 `TemplateCode`。两者必须配套，不能自定义短信内容。
5. 创建独立 RAM 用户和 AccessKey，不使用主账号 AccessKey。仅授予发送与核验权限。

最小 RAM 策略：

```json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dypns:SendSmsVerifyCode",
        "dypns:CheckSmsVerifyCode"
      ],
      "Resource": "*"
    }
  ]
}
```

不要把 AccessKey ID、AccessKey Secret、验证码或真实手机号发送到聊天、Issue、截图或 Git。建议验收后立即停用或轮换临时 RAM AccessKey。

## WSL 临时真发验收

在 WSL 的私密终端中进入 `mvp` 目录。下面的值只进入当前 Shell 环境，不会写入仓库：

```bash
read -r -p "AccessKey ID: " ALIBABA_CLOUD_ACCESS_KEY_ID
read -r -s -p "AccessKey Secret: " ALIBABA_CLOUD_ACCESS_KEY_SECRET
echo
read -r -p "系统赠送 SignName: " MVP_SITE_SMS_SIGN_NAME
read -r -p "系统赠送 TemplateCode: " MVP_SITE_SMS_TEMPLATE_CODE
read -r -p "本次授权测试手机号: " MVP_SITE_SMS_ALLOWED_PHONES

export ALIBABA_CLOUD_ACCESS_KEY_ID
export ALIBABA_CLOUD_ACCESS_KEY_SECRET
export MVP_SITE_SMS_SIGN_NAME
export MVP_SITE_SMS_TEMPLATE_CODE
export MVP_SITE_SMS_ALLOWED_PHONES
export MVP_SITE_SMS_SCHEME_NAME=mvp-login
```

启动最长 30 分钟的受控公网会话：

```bash
./deploy/wsl/start-quick-tunnel.sh \
  --accept-public-demo-risk \
  --site-sms-mode aliyun-dypns \
  --accept-real-sms-cost \
  --duration 1800
```

脚本只允许白名单号码，强制最多 5 条/小时、10 条/日，并禁止自动全流程脚本触发真实短信。测试结束或出现异常时按 `Ctrl+C`；脚本会销毁临时 URL、数据库、日志和随机站点凭据。

结束后清除当前 Shell 中的凭据：

```bash
unset ALIBABA_CLOUD_ACCESS_KEY_ID ALIBABA_CLOUD_ACCESS_KEY_SECRET
unset MVP_SITE_SMS_SIGN_NAME MVP_SITE_SMS_TEMPLATE_CODE
unset MVP_SITE_SMS_ALLOWED_PHONES MVP_SITE_SMS_SCHEME_NAME
```

验收时只有测试手机号和收到的本站 OTP 可以是真实数据。淘宝订单号、支付宝资料、SiliconFlow 用户 ID、奖励流水必须继续使用合成值。客户侧 SiliconFlow 登录仍是 mock，验证码为终端显示的 SiliconFlow demo OTP。

## 通过标准

- 白名单手机号收到系统赠送签名发出的通用登录/注册验证码。
- 站点发送接口不返回 `debug_code`，数据库不保存手机号、OTP、AccessKey 或供应商流水明文。
- 正确验证码登录成功；错误验证码失败；同一验证码不能重复使用。
- 60 秒内不能重发；同一号码每小时最多 5 次；单次验证码最多错误尝试 5 次。
- 未在白名单的手机号不能触发供应商调用。
- 阿里云接口不可用、权限不足或返回非 `PASS` 时失败关闭，不回退到固定验证码。

完成现场真发前，项目状态只能标记为“真实短信代码已接入，账号侧端到端未通过”。
