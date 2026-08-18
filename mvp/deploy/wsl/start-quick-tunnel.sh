#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
accepted_risk=0
accepted_real_sms_cost=0
duration=0
self_test_flow=0
site_sms_mode="mock"

usage() {
  cat <<'EOF'
Usage: ./deploy/wsl/start-quick-tunnel.sh --accept-public-demo-risk [--self-test-flow] [--site-sms-mode MODE] [--accept-real-sms-cost] [--duration SECONDS]

Starts an ephemeral public HTTPS mock demo. Use synthetic data only.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --accept-public-demo-risk)
      accepted_risk=1
      shift
      ;;
    --accept-real-sms-cost)
      accepted_real_sms_cost=1
      shift
      ;;
    --duration)
      if [[ $# -lt 2 ]]; then
        echo "--duration requires a number of seconds." >&2
        exit 2
      fi
      duration="${2:-}"
      shift 2
      ;;
    --self-test-flow)
      self_test_flow=1
      shift
      ;;
    --site-sms-mode)
      if [[ $# -lt 2 ]]; then
        echo "--site-sms-mode requires mock or aliyun-dypns." >&2
        exit 2
      fi
      site_sms_mode="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ${accepted_risk} -ne 1 ]]; then
  echo "Refusing to expose a public demo without --accept-public-demo-risk." >&2
  exit 2
fi
if [[ ! "${duration}" =~ ^[0-9]+$ ]]; then
  echo "--duration must be a non-negative number of seconds." >&2
  exit 2
fi
if [[ "${site_sms_mode}" != "mock" && "${site_sms_mode}" != "aliyun-dypns" ]]; then
  echo "--site-sms-mode must be mock or aliyun-dypns." >&2
  exit 2
fi
if [[ "${site_sms_mode}" == "aliyun-dypns" ]]; then
  if [[ ${accepted_real_sms_cost} -ne 1 ]]; then
    echo "Real SMS acceptance requires --accept-real-sms-cost." >&2
    exit 2
  fi
  if (( duration < 1 || duration > 3600 )); then
    echo "Real SMS acceptance requires --duration between 1 and 3600 seconds." >&2
    exit 2
  fi
  if [[ ${self_test_flow} -eq 1 ]]; then
    echo "--self-test-flow cannot send real SMS." >&2
    exit 2
  fi
  required_sms_variables=(
    ALIBABA_CLOUD_ACCESS_KEY_ID
    ALIBABA_CLOUD_ACCESS_KEY_SECRET
    MVP_SITE_SMS_SIGN_NAME
    MVP_SITE_SMS_TEMPLATE_CODE
    MVP_SITE_SMS_SCHEME_NAME
    MVP_SITE_SMS_ALLOWED_PHONES
  )
  for variable_name in "${required_sms_variables[@]}"; do
    if [[ -z "${!variable_name:-}" ]]; then
      echo "Required real SMS environment variable is missing: ${variable_name}" >&2
      exit 2
    fi
  done
fi
if [[ ${EUID} -eq 0 ]]; then
  echo "Run the demo as your normal WSL user, not as root." >&2
  exit 1
fi
for command_name in cloudflared curl openssl python3; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Required command is missing: ${command_name}" >&2
    exit 1
  fi
done

runtime_dir="$(mktemp -d "${TMPDIR:-/tmp}/sf-mvp-quick-tunnel.XXXXXX")"
chmod 0700 "${runtime_dir}"
database_path="${runtime_dir}/mvp.db"
app_log="${runtime_dir}/app.log"
tunnel_log="${runtime_dir}/cloudflared.log"
isolated_home="${runtime_dir}/home"
mkdir -m 0700 "${isolated_home}"
app_pid=""
tunnel_pid=""

cleanup() {
  if [[ -n "${app_pid}" ]]; then
    kill "${app_pid}" 2>/dev/null || true
    wait "${app_pid}" 2>/dev/null || true
  fi
  if [[ -n "${tunnel_pid}" ]]; then
    kill "${tunnel_pid}" 2>/dev/null || true
    wait "${tunnel_pid}" 2>/dev/null || true
  fi
  rm -rf -- "${runtime_dir}"
}
trap cleanup EXIT INT TERM

port="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
HOME="${isolated_home}" cloudflared tunnel \
  --no-autoupdate \
  --metrics 127.0.0.1:0 \
  --loglevel info \
  --url "http://127.0.0.1:${port}" \
  >"${tunnel_log}" 2>&1 &
tunnel_pid=$!

public_url=""
for _ in {1..60}; do
  if ! kill -0 "${tunnel_pid}" 2>/dev/null; then
    cat "${tunnel_log}" >&2
    exit 1
  fi
  public_url="$(grep -Eo 'https://[-a-z0-9]+\.trycloudflare\.com' \
    "${tunnel_log}" | head -n 1 || true)"
  if [[ -n "${public_url}" ]]; then
    break
  fi
  sleep 1
done
if [[ -z "${public_url}" ]]; then
  cat "${tunnel_log}" >&2
  echo "Timed out waiting for a Quick Tunnel URL." >&2
  exit 1
fi

public_host="${public_url#https://}"
site_otp=""
sms_access_key_id=""
sms_access_key_secret=""
sms_sign_name=""
sms_template_code=""
sms_scheme_name=""
sms_allowed_phones=""
if [[ "${site_sms_mode}" == "mock" ]]; then
  site_otp="$(python3 -c 'import secrets; print(f"{secrets.randbelow(1000000):06d}")')"
else
  sms_access_key_id="${ALIBABA_CLOUD_ACCESS_KEY_ID}"
  sms_access_key_secret="${ALIBABA_CLOUD_ACCESS_KEY_SECRET}"
  sms_sign_name="${MVP_SITE_SMS_SIGN_NAME}"
  sms_template_code="${MVP_SITE_SMS_TEMPLATE_CODE}"
  sms_scheme_name="${MVP_SITE_SMS_SCHEME_NAME}"
  sms_allowed_phones="${MVP_SITE_SMS_ALLOWED_PHONES}"
fi
admin_key="$(openssl rand -hex 24)"

MVP_ENV=development \
MVP_HOST=127.0.0.1 \
MVP_PORT="${port}" \
MVP_DB_PATH="${database_path}" \
MVP_SECRET="$(openssl rand -hex 32)" \
MVP_ADMIN_KEY="${admin_key}" \
MVP_ALLOWED_HOSTS="${public_host},127.0.0.1,localhost" \
MVP_COOKIE_SECURE=1 \
MVP_SILICON_MODE=mock \
MVP_SITE_SMS_MODE="${site_sms_mode}" \
MVP_DEV_SITE_OTP="${site_otp}" \
ALIBABA_CLOUD_ACCESS_KEY_ID="${sms_access_key_id}" \
ALIBABA_CLOUD_ACCESS_KEY_SECRET="${sms_access_key_secret}" \
MVP_SITE_SMS_SIGN_NAME="${sms_sign_name}" \
MVP_SITE_SMS_TEMPLATE_CODE="${sms_template_code}" \
MVP_SITE_SMS_SCHEME_NAME="${sms_scheme_name}" \
MVP_SITE_SMS_ALLOWED_PHONES="${sms_allowed_phones}" \
MVP_SITE_SMS_MAX_SENDS_PER_HOUR=5 \
MVP_SITE_SMS_MAX_SENDS_PER_DAY=10 \
MVP_REMOTE_BROWSER_MODE=disabled \
MVP_SEED_DEMO=0 \
  "${project_root}/run.sh" >"${app_log}" 2>&1 &
app_pid=$!

for _ in {1..60}; do
  if ! kill -0 "${app_pid}" 2>/dev/null; then
    cat "${app_log}" >&2
    exit 1
  fi
  if curl --fail --silent -H "Host: ${public_host}" \
    "http://127.0.0.1:${port}/api/health" >/dev/null; then
    break
  fi
  sleep 1
done

health_payload=""
for _ in {1..60}; do
  if health_payload="$(curl --fail --silent --show-error \
    --connect-timeout 5 "${public_url}/api/health" 2>/dev/null)"; then
    break
  fi
  sleep 1
done
printf '%s' "${health_payload}" | EXPECTED_SITE_SMS_MODE="${site_sms_mode}" python3 -c '
import json, sys
import os
payload = json.load(sys.stdin)
assert payload["status"] == "ok"
assert payload["environment"] == "development"
assert payload["silicon_default_mode"] == "mock"
assert payload["site_sms_mode"] == os.environ["EXPECTED_SITE_SMS_MODE"]
assert payload["remote_browser_mode"] == "disabled"
'

if [[ ${self_test_flow} -eq 1 ]]; then
  QUICK_TUNNEL_BASE_URL="${public_url}" \
  QUICK_TUNNEL_ADMIN_KEY="${admin_key}" \
  QUICK_TUNNEL_SITE_OTP="${site_otp}" \
    python3 "${project_root}/deploy/wsl/quick_tunnel_flow.py"
fi

cat <<EOF

WSL public acceptance session is ready.
Public HTTPS URL: ${public_url}
Admin key: ${admin_key}
SiliconFlow demo OTP: 246810
Site SMS mode: ${site_sms_mode}
EOF

if [[ "${site_sms_mode}" == "mock" ]]; then
  echo "Site login demo OTP: ${site_otp}"
  cat <<'EOF'

Use synthetic data only. Keep this terminal open; press Ctrl+C to destroy the
tunnel, random credentials, logs, and temporary database.
EOF
else
  cat <<'EOF'
Only the configured test phone allowlist can receive real SMS. This session
has a maximum duration of one hour and a hard budget of 5 sends/hour, 10/day.
Only the allowlisted phone and its OTP may be real; all order, Alipay, upstream
account, and payout data must remain synthetic. The session cleans up on exit.
EOF
fi

if (( duration > 0 )); then
  end_time=$((SECONDS + duration))
  while (( SECONDS < end_time )); do
    if ! kill -0 "${app_pid}" 2>/dev/null || ! kill -0 "${tunnel_pid}" 2>/dev/null; then
      echo "The application or tunnel stopped unexpectedly." >&2
      exit 1
    fi
    sleep 1
  done
  exit 0
fi

while true; do
  if ! kill -0 "${app_pid}" 2>/dev/null; then
    cat "${app_log}" >&2
    exit 1
  fi
  if ! kill -0 "${tunnel_pid}" 2>/dev/null; then
    cat "${tunnel_log}" >&2
    exit 1
  fi
  sleep 2
done
