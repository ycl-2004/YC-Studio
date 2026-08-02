#!/usr/bin/env bash
set -euo pipefail

# 迁移必须先成功，Uvicorn 才会启动。
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "[entrypoint] running alembic upgrade head"
    alembic upgrade head
fi

echo "[entrypoint] starting: $*"
exec "$@"
