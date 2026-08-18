#!/usr/bin/env bash
set -euo pipefail

domain="${1:-}"
app_name="siliconflow-invite-task"
python_path="/opt/${app_name}/venv/bin/python"

if [[ -n "${domain}" ]] && { [[ ! "${domain}" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]] || [[ "${domain}" == *..* ]]; }; then
  echo "The domain is invalid." >&2
  exit 2
fi

systemctl is-active --quiet "${app_name}.service"
systemctl is-active --quiet nginx
systemctl is-enabled --quiet "${app_name}-backup.timer"

host_header="${domain:-localhost}"
health_payload="$(curl --fail --silent --show-error -H "Host: ${host_header}" \
  http://127.0.0.1:8765/api/health)"
printf '%s' "${health_payload}" | "${python_path}" -c '
import json, sys
payload = json.load(sys.stdin)
assert payload["status"] == "ok"
assert payload["environment"] == "production"
assert payload["taobao_order_mode"] == "manual"
assert payload["site_sms_mode"] == "disabled"
assert payload["remote_browser_mode"] == "disabled"
'

if [[ -n "${domain}" && -d "/etc/letsencrypt/live/${domain}" ]]; then
  curl --fail --silent --show-error "https://${domain}/api/health" >/dev/null
fi

environment_mode="$(stat -c '%a' "/etc/${app_name}/mvp.env")"
if [[ "${environment_mode}" != "640" ]]; then
  echo "Environment file mode is ${environment_mode}; expected 640." >&2
  exit 1
fi

echo "Deployment verification passed."
