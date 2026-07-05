# Canopy backend — FastAPI + SQLite, one lean glibc image.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first so the layer caches across app-code edits.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# SQLite (and the encrypted OAuth token inside it) lives in /data — the one dir
# the non-root user can write. Mount a volume there to persist across restarts.
# Default the DB here so the image runs standalone, not only under compose.
ENV DATABASE_URL=sqlite:////data/canopy.sqlite3
RUN mkdir -p /data && useradd --system canopy && chown canopy /data
USER canopy
VOLUME /data

EXPOSE 8000

# No curl in slim — probe /health with the stdlib.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
