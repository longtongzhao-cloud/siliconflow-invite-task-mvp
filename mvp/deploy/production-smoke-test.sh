#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
test_host="tasks.example.test"

if command -v python3 >/dev/null 2>&1; then
  python_command="python3"
else
  python_command="python"
fi

port="$(${python_command} -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
database_path="$(mktemp -u "${TMPDIR:-/tmp}/sf-mvp-production.XXXXXX.db")"
log_path="$(mktemp "${TMPDIR:-/tmp}/sf-mvp-production.XXXXXX.log")"

MVP_ENV=production \
MVP_HOST=127.0.0.1 \
MVP_PORT="${port}" \
MVP_DB_PATH="${database_path}" \
MVP_SECRET=test-only-production-secret-material-over-32-bytes \
MVP_ADMIN_KEY=test-only-production-admin-key \
MVP_ALLOWED_HOSTS="${test_host},127.0.0.1,localhost" \
MVP_COOKIE_SECURE=1 \
MVP_SILICON_MODE=manual \
MVP_SITE_SMS_MODE=disabled \
MVP_REMOTE_BROWSER_MODE=disabled \
MVP_SEED_DEMO=0 \
  "${project_root}/run.sh" >"${log_path}" 2>&1 &
server_pid=$!

cleanup() {
  kill "${server_pid}" 2>/dev/null || true
  wait "${server_pid}" 2>/dev/null || true
  rm -f "${database_path}" "${database_path}-shm" "${database_path}-wal" "${log_path}"
}
trap cleanup EXIT

for _ in {1..30}; do
  if ! kill -0 "${server_pid}" 2>/dev/null; then
    cat "${log_path}" >&2
    exit 1
  fi
  if health_payload="$(curl --fail --silent -H "Host: ${test_host}" \
    "http://127.0.0.1:${port}/api/health")"; then
    break
  fi
  sleep 1
done

printf '%s' "${health_payload:-}" | "${python_command}" -c '
import json, sys
payload = json.load(sys.stdin)
assert payload["status"] == "ok"
assert payload["environment"] == "production"
assert payload["taobao_order_mode"] == "manual"
assert payload["silicon_default_mode"] == "manual"
assert payload["site_sms_mode"] == "disabled"
assert payload["remote_browser_mode"] == "disabled"
'

untrusted_status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
  -H 'Host: attacker.example' "http://127.0.0.1:${port}/api/health")"
if [[ "${untrusted_status}" != "400" ]]; then
  echo "Untrusted Host returned ${untrusted_status}; expected 400." >&2
  exit 1
fi

printf '%s\n' "${health_payload}"
