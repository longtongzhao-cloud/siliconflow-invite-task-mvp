#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this script with sudo or as root." >&2
  exit 1
fi
if [[ $# -ne 2 ]]; then
  echo "Usage: sudo $0 tasks.example.com admin@example.com" >&2
  exit 2
fi

domain="$1"
email="$2"
if [[ ! "${domain}" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]] || [[ "${domain}" == *..* ]]; then
  echo "The domain is invalid." >&2
  exit 2
fi
if [[ ! "${email}" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]]; then
  echo "The email address is invalid." >&2
  exit 2
fi
if ! getent ahosts "${domain}" >/dev/null; then
  echo "DNS does not resolve yet; do not request a certificate." >&2
  exit 1
fi

app_name="siliconflow-invite-task"
template_root="/opt/${app_name}/current/deploy/ubuntu/templates"
nginx_site="/etc/nginx/sites-available/${app_name}"

certbot certonly --webroot -w /var/www/letsencrypt \
  --non-interactive --agree-tos --keep-until-expiring \
  --email "${email}" -d "${domain}"

sed "s/__DOMAIN__/${domain}/g" "${template_root}/nginx-https.conf" >"${nginx_site}.tmp"
install -o root -g root -m 0644 "${nginx_site}.tmp" "${nginx_site}"
rm -f "${nginx_site}.tmp"

hook="/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh"
install -d -o root -g root -m 0755 "$(dirname -- "${hook}")"
install -o root -g root -m 0755 "${template_root}/reload-nginx.sh" "${hook}"

nginx -t
systemctl reload nginx
systemctl enable --now certbot.timer
curl --fail --silent --show-error "https://${domain}/api/health" >/dev/null
echo "HTTPS is active for ${domain}."
