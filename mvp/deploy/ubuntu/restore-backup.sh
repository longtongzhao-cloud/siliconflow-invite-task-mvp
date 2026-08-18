#!/usr/bin/env bash
set -euo pipefail

app_name="siliconflow-invite-task"
app_user="siliconflow-mvp"
backup_root="/var/backups/${app_name}"
data_root="/var/lib/${app_name}"
environment_file="/etc/${app_name}/mvp.env"
python_path="/opt/${app_name}/venv/bin/python"
service_stopped=0

# Invoked indirectly by the ERR trap below.
# shellcheck disable=SC2317
restart_after_error() {
  if [[ ${service_stopped} -eq 1 ]]; then
    systemctl start "${app_name}.service" || true
  fi
}
trap restart_after_error ERR

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this script with sudo or as root." >&2
  exit 1
fi
if [[ $# -ne 2 || "$1" != "--confirm" ]]; then
  echo "Usage: sudo $0 --confirm /var/backups/${app_name}/mvp-<timestamp>.db" >&2
  exit 2
fi

selected_backup="$(readlink -f -- "$2")"
case "${selected_backup}" in
  "${backup_root}"/mvp-*.db) ;;
  *)
    echo "The selected backup must be an mvp-*.db file under ${backup_root}." >&2
    exit 2
    ;;
esac
if [[ ! -f "${selected_backup}" ]]; then
  echo "The selected backup does not exist." >&2
  exit 2
fi

integrity="$(${python_path} -c \
  'import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute("PRAGMA integrity_check").fetchone()[0]); c.close()' \
  "${selected_backup}")"
if [[ "${integrity}" != "ok" ]]; then
  echo "The selected backup failed integrity_check." >&2
  exit 1
fi

# Preserve the current state consistently before replacing it.
systemctl start "${app_name}-backup.service"
systemctl stop "${app_name}.service"
service_stopped=1

restore_path="${data_root}/mvp.db.restore"
install -o "${app_user}" -g "${app_user}" -m 0600 \
  "${selected_backup}" "${restore_path}"
rm -f "${data_root}/mvp.db-wal" "${data_root}/mvp.db-shm"
mv -f "${restore_path}" "${data_root}/mvp.db"

systemctl start "${app_name}.service"
service_stopped=0
allowed_hosts="$(sed -n 's/^MVP_ALLOWED_HOSTS=//p' "${environment_file}")"
host_header="${allowed_hosts%%,*}"
for _ in {1..20}; do
  if curl --fail --silent --show-error -H "Host: ${host_header}" \
    http://127.0.0.1:8765/api/health >/dev/null; then
    echo "Backup restored and the application is healthy."
    trap - ERR
    exit 0
  fi
  sleep 1
done

echo "Restore completed, but the application health check failed." >&2
exit 1
