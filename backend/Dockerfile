# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

FROM python:3.12-slim-bookworm AS runtime

# docling's PDF pipeline imports OpenCV, which dynamically loads these X11/GLib
# shared objects even in headless use. Without them every PDF upload fails at
# import time with "libxcb.so.1: cannot open shared object file", while Markdown
# and text uploads succeed — so the gap only shows up on one file type.
RUN apt-get update \
    && apt-get install --no-install-recommends --yes \
        libxcb1 \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 app \
    && useradd --no-log-init --uid 10001 --gid app --create-home app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    # The image builds with `uv sync --no-install-project`, so `app` is a copied
    # directory rather than an installed package. uvicorn and arq happen to find it
    # because sys.path[0] is the working directory, but `python scripts/x.py` sets
    # sys.path[0] to scripts/ and fails on `import app`. Pin the root explicitly so
    # every entry point resolves it the same way.
    PYTHONPATH=/app \
    HF_HOME=/app/.cache/huggingface \
    TRANSFORMERS_CACHE=/app/.cache/huggingface

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app app /app/app
COPY --chown=app:app alembic.ini /app/alembic.ini
COPY --chown=app:app migrations /app/migrations
COPY --chown=app:app scripts/build_indexes.py /app/scripts/build_indexes.py
COPY --chown=app:app scripts/seed_public_libraries.py /app/scripts/seed_public_libraries.py
COPY --chown=app:app seeds /app/seeds
COPY --chown=app:app docker-entrypoint.sh /app/docker-entrypoint.sh

RUN chmod +x /app/docker-entrypoint.sh \
    && mkdir -p /app/.cache/huggingface /app/data/uploads \
    && chown -R app:app /app/.cache /app/data

USER app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
