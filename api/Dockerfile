FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Dependencies first so code edits don't bust the layer cache.
COPY pyproject.toml ./
RUN mkdir canopy && touch canopy/__init__.py && pip install . && rm -rf canopy

COPY canopy ./canopy
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install --no-deps .

# Never run as root.
RUN useradd --create-home --uid 10001 canopy
USER canopy

EXPOSE 8000
CMD ["python", "-m", "canopy", "api"]
