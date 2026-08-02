# YC Studio

[![CI](https://github.com/ycl-2004/YC-Studio/actions/workflows/ci.yml/badge.svg)](https://github.com/ycl-2004/YC-Studio/actions/workflows/ci.yml)

用户上传知识库驱动的内容生成工作台。

上传参考资料建成四层分库 → 跟 Agent 聊出结构化选题卡 → 6 节点工作流生成文章 → 两处人审 → 导出 → 回填效果数据 → 高表现内容回流成新案例。

> 设计文档、实施手册与决策记录全部在 Obsidian vault 的
> `学习资料/百战 AI Agent/实战项目/YC平台/`。
> **本仓库只放代码，不放笔记。**

## 当前进度

| Stage | 状态 |
|:-:|---|
| 0 地基与可观测 | ✅ Step 1–11 本地实现与验收完成（Step 11 待提交） |
| 1–11 | ⬜ 未开始 |

## 结构

```text
backend/     Python + FastAPI，学习重点
frontend/    Stage 0 nginx 占位页；Stage 4 再实现 Vue
```

`backend/app/` 下 14 个模块的职责见 vault 里的《代码目录结构蓝图》。

## 开发

第一次运行先创建本地环境文件，并把示例密码换成本机开发密码；
`POSTGRES_PASSWORD` 和 `DATABASE_URL` 里的密码必须保持一致。

```bash
cp backend/.env.example backend/.env
```

一条命令构建并启动 PostgreSQL + pgvector、Redis、backend、frontend：

```bash
make up                    # 构建四服务并等待全部 healthy
make ps                    # 四个服务都应显示 healthy
make db-check              # 验收 SQLAlchemy async session
make health-check          # 验收 /health、/ready 与数据库故障恢复
make logs                  # 持续查看四服务日志
make down                  # 停止并删除容器，保留数据卷
```

也可以直接运行 `docker compose --env-file backend/.env up --build` 在前台查看启动过程。Backend 启动前会自动执行
`alembic upgrade head`，db/Redis healthy 后才启动 backend，backend healthy 后才启动 frontend。

Frontend、API、PostgreSQL、Redis 分别绑定在 `127.0.0.1:5173`、`127.0.0.1:8000`、
`127.0.0.1:5433`、`127.0.0.1:6380`。数据保存在 Docker
命名卷中；不要运行 `docker compose down -v`，除非确定要删除本地数据。

容器内检查：

```bash
docker compose --env-file backend/.env exec backend whoami
docker compose --env-file backend/.env exec backend alembic current
```

Python 开发命令：

```bash
cd backend
uv sync                  # 装依赖
uv run pytest            # 跑测试
uv run ruff check .      # lint
uv run uvicorn app.main:app --reload   # Step 6 之后可用
```

如果要在宿主机用 `--reload` 开发 backend，只启动依赖后再启动本地进程：

```bash
make infra-up
make dev
```

`make test` / `uv run pytest` 使用 Testcontainers 自动创建临时的 pgvector/PostgreSQL
和 Redis，并在临时数据库中执行 `alembic upgrade head`。测试明确禁止读取
`backend/.env`，也不会连接 `127.0.0.1:5433` 或 `127.0.0.1:6380` 的开发服务；只需保证
Docker Engine 正在运行，不需要先执行 `make up`。每个测试结束后会回滚外层 transaction，
即使被测代码调用了 `commit()`，也不会把测试 User 留到下一个测试。

## 持续集成

push 到 `main` 或创建面向 `main` 的 Pull Request 时，GitHub Actions 会在 Ubuntu runner 上
启动独立的 pgvector/PostgreSQL 与 Redis service containers，然后执行锁定依赖同步、Ruff
format/lint、mypy、pytest 和 Alembic drift check。CI 使用固定测试凭证和独立环境变量，不读取
开发 `.env`，也不需要 GitHub repository secrets。

应用运行后，GET /health 只检查进程存活；GET /ready 会实际检查 PostgreSQL
与 Redis。依赖暂时不可用时，/ready 返回 503，但 /health 仍保持 200。

## Python 版本说明

`requires-python = ">=3.12,<3.14"`。

本机装的是 3.14，但**上限刻意卡在 3.14 以下**：Stage 1 会用到 `torch` / `sentence-transformers`，这类重型 ML 库对新 Python 版本的支持通常滞后半年到一年。

```bash
uv python pin 3.12    # 建议
```

如果想用 3.14，先单独验证 `torch` 和 `sentence-transformers` 能装上再改上限。

## 已知限制

> 项目完成后在这里如实列出。写得出局限才说明真的做过。
