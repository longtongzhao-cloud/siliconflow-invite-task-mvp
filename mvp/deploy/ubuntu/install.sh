#!/usr/bin/env bash
set -euo pipefail

app_name="siliconflow-invite-task"
app_user="siliconflow-mvp"
app_root="/opt/${app_name}"
config_root="/etc/${app_name}"
data_root="/var/lib/${app_name}"
backup_root="/var/backups/${app_name}"
domain=""
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"

usage() {
  cat <<'EOF'
Usage: sudo ./deploy/ubuntu/install.sh --domain tasks.example.com [--source /path/to/mvp]

Installs the current source as a single-node Ubuntu test deployment. It starts
HTTP only. Run enable-tls.sh after public DNS points to this server.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain)
      domain="${2:-}"
      shift 2
      ;;
    --source)
      source_dir="${2:-}"
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

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this installer with sudo or as root." >&2
  exit 1
fi
if [[ ! "${domain}" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]] || [[ "${domain}" == *..* ]]; then
  echo "--domain must be a lower-case DNS hostname." >&2
  exit 2
fi
source_dir="$(cd -- "${source_dir}" && pwd)"
if [[ ! -f "${source_dir}/mvp_app/main.py" || ! -f "${source_dir}/requirements.txt" ]]; then
  echo "--source must point to the mvp directory." >&2
  exit 2
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl nginx openssl python3 python3-venv rsync ufw \
  certbot

if ! getent passwd "${app_user}" >/dev/null; then
  useradd --system --home-dir "${data_root}" --create-home --shell /usr/sbin/nologin "${app_user}"
fi

install -d -o root -g root -m 0755 "${app_root}" "${app_root}/releases"
install -d -o "${app_user}" -g "${app_user}" -m 0700 "${data_root}" "${backup_root}"
install -d -o root -g "${app_user}" -m 0750 "${config_root}"
install -d -o www-data -g www-data -m 0755 /var/www/letsencrypt

release_id="$(date -u +%Y%m%dT%H%M%SZ)"
release_dir="${app_root}/releases/${release_id}"
install -d -o root -g root -m 0755 "${release_dir}"
rsync -a --delete \
  --exclude '.venv/' --exclude '.pytest_cache/' --exclude '__pycache__/' \
  --exclude 'data/' --exclude '*.db' --exclude '*.log' \
  "${source_dir}/" "${release_dir}/"
chown -R root:root "${release_dir}"

if [[ ! -x "${app_root}/venv/bin/python" ]]; then
  python3 -m venv "${app_root}/venv"
fi
"${app_root}/venv/bin/python" -m pip install \
  --disable-pip-version-check --no-cache-dir -r "${release_dir}/requirements.txt"

environment_file="${config_root}/mvp.env"
if [[ ! -f "${environment_file}" ]]; then
  umask 0077
  secret="$(openssl rand -hex 32)"
  admin_key="$(openssl rand -hex 24)"
  cat >"${environment_file}" <<EOF
MVP_ENV=production
MVP_HOST=127.0.0.1
MVP_PORT=8765
MVP_DB_PATH=${data_root}/mvp.db
MVP_SECRET=${secret}
MVP_ADMIN_KEY=${admin_key}
MVP_ALLOWED_HOSTS=${domain},127.0.0.1,localhost
MVP_SILICON_MODE=manual
MVP_SITE_SMS_MODE=disabled
MVP_REMOTE_BROWSER_MODE=disabled
MVP_SEED_DEMO=0
EOF
  chown root:"${app_user}" "${environment_file}"
  chmod 0640 "${environment_file}"
else
  allowed_hosts="$(sed -n 's/^MVP_ALLOWED_HOSTS=//p' "${environment_file}")"
  case ",${allowed_hosts}," in
    *",${domain},"*) ;;
    *)
      echo "Existing ${environment_file} does not allow ${domain}. Update it before retrying." >&2
      exit 1
      ;;
  esac
fi

ln -sfn "${release_dir}" "${app_root}/current.next"
mv -Tf "${app_root}/current.next" "${app_root}/current"

template_root="${release_dir}/deploy/ubuntu/templates"
install -o root -g root -m 0644 \
  "${template_root}/${app_name}.service" "/etc/systemd/system/${app_name}.service"
install -o root -g root -m 0644 \
  "${template_root}/${app_name}-backup.service" "/etc/systemd/system/${app_name}-backup.service"
install -o root -g root -m 0644 \
  "${template_root}/${app_name}-backup.timer" "/etc/systemd/system/${app_name}-backup.timer"

nginx_site="/etc/nginx/sites-available/${app_name}"
sed "s/__DOMAIN__/${domain}/g" "${template_root}/nginx-http.conf" >"${nginx_site}.tmp"
install -o root -g root -m 0644 "${nginx_site}.tmp" "${nginx_site}"
rm -f "${nginx_site}.tmp" /etc/nginx/sites-enabled/default
ln -sfn "${nginx_site}" "/etc/nginx/sites-enabled/${app_name}"

nginx -t
systemctl daemon-reload
systemctl enable "${app_name}.service"
systemctl restart "${app_name}.service"
systemctl enable --now "${app_name}-backup.timer"
systemctl enable --now nginx
systemctl reload nginx

for _ in {1..20}; do
  if curl --fail --silent --show-error -H "Host: ${domain}" \
    http://127.0.0.1:8765/api/health >/dev/null; then
    break
  fi
  sleep 1
done
curl --fail --silent --show-error -H "Host: ${domain}" \
  http://127.0.0.1:8765/api/health >/dev/null

cat <<EOF
Installed release ${release_id}.
HTTP bootstrap is ready for ACME only: http://${domain}
Secrets: ${environment_file} (not printed)

Next steps:
  1. Point the DNS A record for ${domain} to this server.
  2. Run deploy/ubuntu/configure-firewall.sh with the actual SSH port.
  3. Run deploy/ubuntu/enable-tls.sh ${domain} you@example.com.
  4. Do not use the application over HTTP. Run deploy/ubuntu/verify.sh ${domain} after TLS succeeds.
EOF
