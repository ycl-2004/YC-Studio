.PHONY: help sync dev test lint typecheck up down ps logs db-check migration-check app-check logging-check

COMPOSE := docker compose --env-file backend/.env

help:
	@echo "sync       装依赖"
	@echo "dev        起开发服务器"
	@echo "test       跑测试                [Step 9 之后可用]"
	@echo "lint       ruff 检查             [Step 10 之后可用]"
	@echo "typecheck  mypy 检查             [Step 10 之后可用]"
	@echo "up         起依赖服务            [Step 3 之后可用]"
	@echo "down       停依赖服务"
	@echo "ps         看依赖服务状态"
	@echo "logs       看容器日志"
	@echo "db-check   验收 async 数据库基础设施"
	@echo "migration-check  验收 Alembic revision、users schema 与零残留约束探针"
	@echo "app-check  验收 FastAPI lifespan、路由前缀、OpenAPI 与 CORS"
	@echo "logging-check  验收 request_id、生产 JSON、Uvicorn/SQLAlchemy 与异常日志"

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

up:
	$(COMPOSE) up -d db redis

down:
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f db redis

db-check:
	cd backend && uv run python scripts/check_db.py

migration-check:
	cd backend && uv run python scripts/check_migrations.py

app-check:
	cd backend && uv run python scripts/check_app.py

logging-check:
	cd backend && uv run python scripts/check_logging.py
