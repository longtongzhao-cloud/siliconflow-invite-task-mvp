from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path


MVP_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_ROOT = MVP_ROOT / "deploy"
TEMPLATE_ROOT = DEPLOY_ROOT / "ubuntu" / "templates"


def test_sqlite_backup_is_consistent_and_prunes_expired_files(
    tmp_path: Path,
) -> None:
    database = tmp_path / "source.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA wal_autocheckpoint = 0")
        connection.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO sample(value) VALUES('expected')")
        connection.commit()

        expired = backup_dir / "mvp-20000101T000000000000Z.db"
        expired.write_bytes(b"expired")
        old_time = time.time() - 9 * 24 * 3600
        os.utime(expired, (old_time, old_time))

        completed = subprocess.run(
            [
                sys.executable,
                str(DEPLOY_ROOT / "backup_sqlite.py"),
                "--database",
                str(database),
                "--backup-dir",
                str(backup_dir),
                "--retention-days",
                "7",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        connection.close()
    backup = Path(completed.stdout.strip())

    assert backup.parent == backup_dir
    assert backup.exists()
    assert not expired.exists()
    with sqlite3.connect(backup) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT value FROM sample").fetchone()[0] == "expected"


def test_systemd_service_is_single_process_and_hardened() -> None:
    service = (TEMPLATE_ROOT / "siliconflow-invite-task.service").read_text(
        encoding="utf-8"
    )

    assert "User=siliconflow-mvp" in service
    assert "EnvironmentFile=/etc/siliconflow-invite-task/mvp.env" in service
    assert "--host 127.0.0.1 --port 8765" in service
    assert "--proxy-headers --forwarded-allow-ips=127.0.0.1" in service
    assert "--workers" not in service
    assert "ProtectSystem=strict" in service
    assert "ReadWritePaths=/var/lib/siliconflow-invite-task" in service
    assert "NoNewPrivileges=true" in service


def test_nginx_templates_proxy_only_to_loopback() -> None:
    http_template = (TEMPLATE_ROOT / "nginx-http.conf").read_text(encoding="utf-8")
    assert "server_name __DOMAIN__;" in http_template
    assert "location ^~ /.well-known/acme-challenge/" in http_template
    assert "return 503;" in http_template
    assert "proxy_pass" not in http_template

    https_template = (TEMPLATE_ROOT / "nginx-https.conf").read_text(
        encoding="utf-8"
    )
    assert "server_name __DOMAIN__;" in https_template
    assert "proxy_pass http://127.0.0.1:8765;" in https_template
    assert "proxy_set_header Host $host;" in https_template
    assert "client_max_body_size 1m;" in https_template
    assert "proxy_pass http://0.0.0.0" not in https_template
    assert "server_name _;" not in https_template
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in https_template
    assert "Strict-Transport-Security" in https_template


def test_installer_generates_fail_closed_production_modes() -> None:
    installer = (DEPLOY_ROOT / "ubuntu" / "install.sh").read_text(
        encoding="utf-8"
    )

    assert "MVP_ENV=production" in installer
    assert "MVP_ALLOWED_HOSTS=${domain},127.0.0.1,localhost" in installer
    assert "MVP_COOKIE_SECURE=1" in installer
    assert "MVP_SILICON_MODE=manual" in installer
    assert "MVP_SITE_SMS_MODE=disabled" in installer
    assert "MVP_REMOTE_BROWSER_MODE=disabled" in installer
    assert "MVP_SEED_DEMO=0" in installer
    assert "ufw --force enable" not in installer

    restore = (DEPLOY_ROOT / "ubuntu" / "restore-backup.sh").read_text(
        encoding="utf-8"
    )
    assert '"$1" != "--confirm"' in restore
    assert "PRAGMA integrity_check" in restore
    assert 'systemctl start "${app_name}-backup.service"' in restore
    assert 'systemctl stop "${app_name}.service"' in restore
    assert "restart_after_error" in restore


def test_quick_tunnel_requires_explicit_risk_and_ephemeral_data() -> None:
    script = (DEPLOY_ROOT / "wsl" / "start-quick-tunnel.sh").read_text(
        encoding="utf-8"
    )

    assert "--accept-public-demo-risk" in script
    assert "mktemp -d" in script
    assert 'MVP_DB_PATH="${database_path}"' in script
    assert "MVP_COOKIE_SECURE=1" in script
    assert 'MVP_ALLOWED_HOSTS="${public_host},127.0.0.1,localhost"' in script
    assert "MVP_SEED_DEMO=0" in script
    assert 'rm -rf -- "${runtime_dir}"' in script
    assert "*.trycloudflare.com" not in script
    assert "--self-test-flow" in script
    assert "--accept-real-sms-cost" in script
    assert "MVP_SITE_SMS_ALLOWED_PHONES" in script
    assert "duration < 1 || duration > 3600" in script
    assert "--self-test-flow cannot send real SMS" in script
    assert "MVP_SITE_SMS_MAX_SENDS_PER_HOUR=5" in script
    assert "MVP_SITE_SMS_MAX_SENDS_PER_DAY=10" in script

    flow = (DEPLOY_ROOT / "wsl" / "quick_tunnel_flow.py").read_text(
        encoding="utf-8"
    )
    assert "HTTPCookieProcessor" in flow
    assert "cookie.secure" in flow
    assert '"PAYOUT_PENDING"' in flow
    assert '"PAID"' in flow
