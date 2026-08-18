#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
accepted_risk=0
duration=0
self_test_flow=0

usage() {
  cat <<'EOF'
Usage: ./deploy/wsl/start-quick-tunnel.sh --accept-public-demo-risk [--self-test-flow] [--duration SECONDS]

Starts an ephemeral public HTTPS mock demo. Use synthetic data only.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --accept-public-demo-risk)
      accepted_risk=1
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
site_otp="$(python3 -c 'import secrets; print(f"{secrets.randbelow(1000000):06d}")')"
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
MVP_SITE_SMS_MODE=mock \
MVP_DEV_SITE_OTP="${site_otp}" \
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
printf '%s' "${health_payload}" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
assert payload["status"] == "ok"
assert payload["environment"] == "development"
assert payload["silicon_default_mode"] == "mock"
assert payload["site_sms_mode"] == "mock"
assert payload["remote_browser_mode"] == "disabled"
'

if [[ ${self_test_flow} -eq 1 ]]; then
  QUICK_TUNNEL_BASE_URL="${public_url}" \
  QUICK_TUNNEL_ADMIN_KEY="${admin_key}" \
  QUICK_TUNNEL_SITE_OTP="${site_otp}" \
    python3 "${project_root}/deploy/wsl/quick_tunnel_flow.py"
fi

cat <<EOF

WSL public mock demo is ready.
Public HTTPS URL: ${public_url}
Admin key: ${admin_key}
Site login demo OTP: ${site_otp}
SiliconFlow demo OTP: 246810

Use synthetic data only. Keep this terminal open; press Ctrl+C to destroy the
tunnel, random credentials, logs, and temporary database.
EOF

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
