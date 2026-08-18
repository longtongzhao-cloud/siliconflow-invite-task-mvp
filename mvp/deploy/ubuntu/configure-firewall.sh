#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this script with sudo or as root." >&2
  exit 1
fi
if [[ $# -ne 2 || "$1" != "--ssh-port" || ! "$2" =~ ^[0-9]+$ ]]; then
  echo "Usage: sudo $0 --ssh-port 22" >&2
  exit 2
fi

ssh_port="$2"
if (( ssh_port < 1 || ssh_port > 65535 )); then
  echo "The SSH port must be between 1 and 65535." >&2
  exit 2
fi

ufw default deny incoming
ufw default allow outgoing
ufw allow "${ssh_port}/tcp" comment 'SSH'
ufw allow 'Nginx Full'
ufw --force enable
ufw status verbose
