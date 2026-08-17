#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ -n "${MVP_VENV_PATH:-}" ]]; then
  venv_root="${MVP_VENV_PATH}"
elif [[ -r /proc/sys/kernel/osrelease ]] && grep -qi microsoft /proc/sys/kernel/osrelease; then
  venv_root="${XDG_CACHE_HOME:-${HOME}/.cache}/siliconflow-invite-task-mvp/venv"
else
  venv_root="${project_root}/.venv"
fi

if command -v python3 >/dev/null 2>&1; then
  bootstrap_python="python3"
elif command -v python >/dev/null 2>&1; then
  bootstrap_python="python"
else
  echo "Python 3.11 or newer is required." >&2
  exit 1
fi

if [[ ! -x "${venv_root}/bin/python" && ! -x "${venv_root}/Scripts/python.exe" ]]; then
  "${bootstrap_python}" -m venv "${venv_root}"
fi

if [[ -x "${venv_root}/bin/python" ]]; then
  venv_python="${venv_root}/bin/python"
else
  venv_python="${venv_root}/Scripts/python.exe"
fi

"${venv_python}" -m pip install --disable-pip-version-check -q \
  -r "${project_root}/requirements.txt"

export MVP_ENV="${MVP_ENV:-development}"
export MVP_DB_PATH="${MVP_DB_PATH:-${project_root}/data/mvp.db}"
export MVP_SILICON_MODE="${MVP_SILICON_MODE:-mock}"
export MVP_SITE_SMS_MODE="${MVP_SITE_SMS_MODE:-mock}"
export MVP_REMOTE_BROWSER_MODE="${MVP_REMOTE_BROWSER_MODE:-disabled}"
export MVP_SEED_DEMO="${MVP_SEED_DEMO:-1}"
export MVP_SECRET="${MVP_SECRET:-local-mvp-secret-change-before-production}"
export MVP_ADMIN_KEY="${MVP_ADMIN_KEY:-mvp-admin-demo}"

cd "${project_root}"
exec "${venv_python}" -m uvicorn mvp_app.main:app \
  --host "${MVP_HOST:-127.0.0.1}" \
  --port "${MVP_PORT:-8765}"
