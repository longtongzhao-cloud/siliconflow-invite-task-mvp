#!/usr/bin/env bash
set -euo pipefail

deploy_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
template_root="${deploy_root}/ubuntu/templates"
verify_root="$(mktemp -d "${TMPDIR:-/tmp}/siliconflow-deploy-verify.XXXXXX")"

cleanup() {
  rm -rf -- "${verify_root}"
}
trap cleanup EXIT

while IFS= read -r -d '' script; do
  bash -n "${script}"
done < <(find "${deploy_root}" -name '*.sh' -print0)

if command -v shellcheck >/dev/null 2>&1; then
  find "${deploy_root}" -name '*.sh' -print0 | xargs -0 shellcheck
fi

if command -v systemd-analyze >/dev/null 2>&1; then
  sed "s#/opt/siliconflow-invite-task/venv/bin/python#/usr/bin/python3#g" \
    "${template_root}/siliconflow-invite-task.service" \
    >"${verify_root}/siliconflow-invite-task.service"
  sed "s#/opt/siliconflow-invite-task/venv/bin/python#/usr/bin/python3#g" \
    "${template_root}/siliconflow-invite-task-backup.service" \
    >"${verify_root}/siliconflow-invite-task-backup.service"
  cp "${template_root}/siliconflow-invite-task-backup.timer" "${verify_root}/"
  chmod 0644 "${verify_root}"/*.service "${verify_root}"/*.timer
  systemd-analyze verify \
    "${verify_root}/siliconflow-invite-task.service" \
    "${verify_root}/siliconflow-invite-task-backup.service" \
    "${verify_root}/siliconflow-invite-task-backup.timer"
fi

if command -v nginx >/dev/null 2>&1 && command -v openssl >/dev/null 2>&1; then
  cat >"${verify_root}/nginx.conf" <<EOF
pid ${verify_root}/nginx.pid;
error_log stderr;
events {}
http {
    include /etc/nginx/mime.types;
    access_log off;
    include ${verify_root}/site.conf;
}
EOF

  sed "s/__DOMAIN__/tasks.example.com/g" \
    "${template_root}/nginx-http.conf" >"${verify_root}/site.conf"
  nginx -t -c "${verify_root}/nginx.conf" -p "${verify_root}"

  openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
    -subj /CN=tasks.example.com \
    -keyout "${verify_root}/key.pem" -out "${verify_root}/cert.pem" \
    >/dev/null 2>&1
  sed \
    -e "s/__DOMAIN__/tasks.example.com/g" \
    -e "s#/etc/letsencrypt/live/tasks.example.com/fullchain.pem#${verify_root}/cert.pem#" \
    -e "s#/etc/letsencrypt/live/tasks.example.com/privkey.pem#${verify_root}/key.pem#" \
    "${template_root}/nginx-https.conf" >"${verify_root}/site.conf"
  nginx -t -c "${verify_root}/nginx.conf" -p "${verify_root}"
fi

echo "Deployment asset validation passed."
