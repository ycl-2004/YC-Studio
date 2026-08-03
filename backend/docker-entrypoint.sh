#!/usr/bin/env bash
set -euo pipefail

# 迁移必须先成功，Uvicorn 才会启动。
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "[entrypoint] running alembic upgrade head"
    alembic upgrade head
fi

if [ "${SEED_PUBLIC_LIBRARIES:-0}" = "1" ]; then
    echo "[entrypoint] synchronizing version-controlled public libraries"
    python scripts/seed_public_libraries.py
fi

echo "[entrypoint] starting: $*"
exec "$@"
