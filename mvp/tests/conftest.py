from __future__ import annotations

import os


os.environ["MVP_ENV"] = "development"
os.environ["MVP_SEED_DEMO"] = "0"
os.environ["MVP_ADMIN_KEY"] = "mvp-admin-demo"
os.environ["MVP_SECRET"] = "test-only-secret-with-more-than-32-bytes"
os.environ["MVP_SITE_SMS_MODE"] = "mock"
os.environ["MVP_REMOTE_BROWSER_MODE"] = "disabled"
