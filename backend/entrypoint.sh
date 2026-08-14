#!/bin/sh
# Migrate + ingest catalog on start (fine for one instance; revisit if you scale).
# seed_cards is idempotent. Do not call setup_dev here — that resets demo users.
# exec gunicorn so SIGTERM reaches the worker; --timeout 120 for heavy requests.
set -e

python manage.py migrate --noinput
python manage.py seed_cards
# PORT is injected by Render; default 8000 for local compose.
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-120}"
