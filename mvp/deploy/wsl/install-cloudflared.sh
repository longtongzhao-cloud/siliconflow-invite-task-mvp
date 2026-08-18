#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this installer with sudo or as root." >&2
  exit 1
fi

apt-get update
apt-get install -y --no-install-recommends ca-certificates curl
install -d -o root -g root -m 0755 /usr/share/keyrings
curl --fail --silent --show-error --location \
  https://pkg.cloudflare.com/cloudflare-main.gpg \
  --output /usr/share/keyrings/cloudflare-main.gpg
chmod 0644 /usr/share/keyrings/cloudflare-main.gpg
printf '%s\n' \
  'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' \
  >/etc/apt/sources.list.d/cloudflared.list

apt-get update
apt-get install -y --no-install-recommends cloudflared
cloudflared --version
