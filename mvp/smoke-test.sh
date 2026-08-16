#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ -n "${MVP_SMOKE_PORT:-}" ]]; then
  port="${MVP_SMOKE_PORT}"
elif command -v python3 >/dev/null 2>&1; then
  port="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
else
  port="$(python -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
fi

database_path="$(mktemp -u "${TMPDIR:-/tmp}/sf-mvp-smoke.XXXXXX.db")"
log_path="$(mktemp "${TMPDIR:-/tmp}/sf-mvp-smoke.XXXXXX.log")"

MVP_PORT="${port}" MVP_DB_PATH="${database_path}" \
  "${project_root}/run.sh" >"${log_path}" 2>&1 &
server_pid=$!

cleanup() {
  kill "${server_pid}" 2>/dev/null || true
  wait "${server_pid}" 2>/dev/null || true
  rm -f "${database_path}" "${database_path}-shm" "${database_path}-wal" "${log_path}"
}
trap cleanup EXIT

for attempt in {1..30}; do
  if ! kill -0 "${server_pid}" 2>/dev/null; then
    cat "${log_path}" >&2
    exit 1
  fi
  if health_payload="$(curl --fail --silent "http://127.0.0.1:${port}/api/health")"; then
    printf '%s\n' "${health_payload}"
    exit 0
  fi
  sleep 1
done

cat "${log_path}" >&2
exit 1
