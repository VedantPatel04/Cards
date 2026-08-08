import os

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

from .base import * #noqa: F403

DEBUG = True

# Local-only fallback so manage.py works before .env exists.
SECRET_KEY = os.environ.get("SECRET_KEY", "local-dev-secret-key-not-for-production")

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Same shape as production: one DATABASE_URL. No ssl_require for local
# (host or docker-compose service) typically does not speak TLS.
_database_url = os.environ.get("DATABASE_URL")
if not _database_url:
    raise ImproperlyConfigured(
        "DATABASE_URL is not set. Add it to backend/.env (see .env.example)."
    )

DATABASES = {
    "default": dj_database_url.parse(
        _database_url,
        conn_max_age=60,
        conn_health_checks=True,
        ssl_require=False,
    )
}
