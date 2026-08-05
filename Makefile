.PHONY: help sync dev dev-backend dev-frontend frontend-install migrate test lint typecheck \
        build up infra-up down ps logs db-check migration-check app-check logging-check \
        health-check seed-public

COMPOSE := docker compose --env-file backend/.env

help:
	@echo "── 启动全栈 ──────────────────────────────────────────────"
	@echo "up           容器全栈：db + redis + backend + worker + frontend"
	@echo "             → http://127.0.0.1:5173 （连真实 API）"
	@echo "dev          本地全栈热重载：容器只跑 db + redis，"
	@echo "             backend / worker / frontend 跑在宿主机，Ctrl-C 一起停"
	@echo "             → http://127.0.0.1:5173 + http://127.0.0.1:8000"
	@echo "dev-backend  只跑本地 backend（--reload）"
	@echo "dev-frontend 只跑本地 frontend（mock 数据，不需要后端）"
	@echo "infra-up     只启动 PostgreSQL + Redis"
	@echo "down         停止并移除容器（保留 named volumes）"
	@echo ""
	@echo "── 开发 ─────────────────────────────────────────────────"
	@echo "sync         装 backend 依赖"
	@echo "frontend-install  装 frontend 依赖（已装则跳过）"
	@echo "migrate      alembic upgrade head"
	@echo "test         用隔离容器跑完整 pytest 测试"
	@echo "lint         ruff 检查"
	@echo "typecheck    mypy 检查"
	@echo "build        构建 backend/frontend 镜像"
	@echo "ps           看服务状态"
	@echo "logs         跟踪服务日志"
	@echo ""
	@echo "── 验收 / 数据 ──────────────────────────────────────────"
	@echo "db-check     验收 async 数据库基础设施"
	@echo "migration-check  验收 Alembic revision、users schema 与零残留约束探针"
	@echo "app-check    验收 FastAPI lifespan、路由前缀、OpenAPI 与 CORS"
	@echo "logging-check    验收 request_id、生产 JSON、Uvicorn/SQLAlchemy 与异常日志"
	@echo "health-check     验收 liveness、readiness、数据库故障与自动恢复"
	@echo "seed-public  初始化或同步版本化公共规则库与模板库"

sync:
	cd backend && uv sync

frontend-install:
	@[ -d frontend/node_modules ] || (cd frontend && npm install)

migrate:
	cd backend && uv run alembic upgrade head

# One command for the whole stack in reload mode. The containerised backend/worker/
# frontend are stopped first: they bind the same host ports and the same database, so
# leaving them up means requests silently land on the image instead of your working
# tree. db and redis stay in Docker because nothing is gained by running them locally.
#
# The worker runs on the host too, not in Docker: batch uploads write their bytes to
# backend/data/uploads, while the container worker only sees the upload_data volume —
# a split that makes every queued file fail with "file not found".
dev: frontend-install
	$(COMPOSE) up -d db redis
	-$(COMPOSE) stop backend worker frontend
	$(MAKE) migrate
	@echo ""
	@echo "  backend   http://127.0.0.1:8000   (--reload)"
	@echo "  frontend  http://127.0.0.1:5173   (VITE_USE_MOCK=false → 真实 API)"
	@echo "  Ctrl-C 一次同时停掉三个进程"
	@echo ""
	@trap 'kill 0' EXIT INT TERM; \
	  (cd backend && uv run uvicorn app.main:app --reload --port 8000) & \
	  (cd backend && uv run arq app.tasks.worker.WorkerSettings) & \
	  (cd frontend && VITE_USE_MOCK=false npm run dev) & \
	  wait

dev-backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

# No backend needed: the mock layer answers every call in the browser.
dev-frontend: frontend-install
	cd frontend && npm run dev

test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check .

typecheck:
	cd backend && uv run mypy app

build:
	$(COMPOSE) build backend frontend

up:
	$(COMPOSE) up -d --build --wait

infra-up:
	$(COMPOSE) up -d db redis

down:
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f

db-check:
	cd backend && uv run python scripts/check_db.py

migration-check:
	cd backend && uv run python scripts/check_migrations.py

app-check:
	cd backend && uv run python scripts/check_app.py

logging-check:
	cd backend && uv run python scripts/check_logging.py

health-check:
	cd backend && uv run python scripts/check_health.py

seed-public:
	cd backend && uv run python scripts/seed_public_libraries.py
