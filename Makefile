.PHONY: help sync dev test lint typecheck up down ps logs

COMPOSE := docker compose --env-file backend/.env

help:
	@echo "sync       装依赖"
	@echo "dev        起开发服务器          [Step 6 之后可用]"
	@echo "test       跑测试                [Step 9 之后可用]"
	@echo "lint       ruff 检查             [Step 10 之后可用]"
	@echo "typecheck  mypy 检查             [Step 10 之后可用]"
	@echo "up         起依赖服务            [Step 3 之后可用]"
	@echo "down       停依赖服务"
	@echo "ps         看依赖服务状态"
	@echo "logs       看容器日志"

sync:
	cd backend && uv sync

dev:
	cd backend && uv run uvicorn ycstudio.main:app --reload

test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check .

typecheck:
	cd backend && uv run mypy src

up:
	$(COMPOSE) up -d db redis

down:
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f db redis
