.PHONY: help sync dev test lint typecheck build up infra-up down ps logs db-check migration-check app-check logging-check health-check seed-public

COMPOSE := docker compose --env-file backend/.env

help:
	@echo "sync       装依赖"
	@echo "dev        起开发服务器"
	@echo "test       用隔离容器跑完整 pytest 测试"
	@echo "lint       ruff 检查             [Step 10 之后可用]"
	@echo "typecheck  mypy 检查             [Step 10 之后可用]"
	@echo "build      构建 backend/frontend 镜像"
	@echo "up         构建并启动四服务全栈"
	@echo "infra-up   只启动 PostgreSQL + Redis"
	@echo "down       停止并移除容器（保留 named volumes）"
	@echo "ps         看四服务状态"
	@echo "logs       跟踪四服务日志"
	@echo "db-check   验收 async 数据库基础设施"
	@echo "migration-check  验收 Alembic revision、users schema 与零残留约束探针"
	@echo "app-check  验收 FastAPI lifespan、路由前缀、OpenAPI 与 CORS"
	@echo "logging-check  验收 request_id、生产 JSON、Uvicorn/SQLAlchemy 与异常日志"
	@echo "health-check  验收 liveness、readiness、数据库故障与自动恢复"
	@echo "seed-public  初始化或同步版本化公共规则库与模板库"

sync:
	cd backend && uv sync

dev:
	cd backend && uv run uvicorn app.main:app --reload

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
