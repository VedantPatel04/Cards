#!/bin/sh
# Migrate on start (fine for one instance; revisit if you scale horizontally).
# No seeding here — run seeds as one-shot management commands after deploy.
# exec gunicorn so SIGTERM reaches the worker; --timeout 120 for heavy requests.
set -e

python manage.py migrate --noinput

# PORT is injected by Render; default 8000 for local compose.
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-120}"
