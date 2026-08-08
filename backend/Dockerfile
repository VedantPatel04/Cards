# Render + local compose share this image
# Python 3.12 (not Mac venv 3.14): pin a supported CPython; change deliberately.
#for now, NOT INCLUDED: WhiteNoise (JSON API), multi-stage build, non-root user.
# a platform builds a 'container image': OS + Python + dependencies and code -- > Three layers: Image recipe --> Start script --> local rehearsal
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

# libpq runtime for psycopg2-binary on some platforms; keep the image minimal.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x entrypoint.sh

# Render sets PORT; local compose maps 8000.
EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
