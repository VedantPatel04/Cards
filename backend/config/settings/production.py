import os

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False

_secret = os.environ.get("SECRET_KEY")
if not _secret:
    raise ImproperlyConfigured(
        "SECRET_KEY must be set in the environment for production."
    )
SECRET_KEY = _secret

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", "").split(",")
    if host.strip()
]
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "ALLOWED_HOSTS must be set in the environment for production "
        "(comma-separated hostnames)."
    )

_database_url = os.environ.get("DATABASE_URL")
if not _database_url:
    raise ImproperlyConfigured(
        "DATABASE_URL must be set in the environment for production."
    )

# Default true for Supabase/Render. docker-compose sets DATABASE_SSL_REQUIRE=false
# because the local Postgres image does not speak TLS.
_ssl_require = os.environ.get("DATABASE_SSL_REQUIRE", "true").lower() in (
    "1",
    "true",
    "yes",
)

DATABASES = {
    "default": dj_database_url.parse(
        _database_url,
        conn_max_age=60,
        conn_health_checks=True,
        ssl_require=_ssl_require,
    )
}

# Redis is required for merchant cache in production fail loudly if omitted so a misconfigured deploy does not silently point at localhost inside the container.
if not os.environ.get("REDIS_URL"):
    raise ImproperlyConfigured(
        "REDIS_URL must be set in the environment for production."
    )
REDIS_URL = os.environ["REDIS_URL"]

# Render terminate TLS at the proxy and forward HTTP to the app.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Default on for real deploys; docker-compose can set SECURE_SSL_REDIRECT=false so local HTTP to the web container is not permanently redirected.
SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "true").lower() in (
    "1",
    "true",
    "yes",
)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Browser clients (future Vercel origin) that POST with cookies/CSRF need this. JWT API calls from JS do not rely on CSRF, but admin might later.
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
