# YC Studio

用户上传知识库驱动的内容生成工作台。

上传参考资料建成四层分库 → 跟 Agent 聊出结构化选题卡 → 6 节点工作流生成文章 → 两处人审 → 导出 → 回填效果数据 → 高表现内容回流成新案例。

> 设计文档、实施手册与决策记录全部在 Obsidian vault 的
> `学习资料/百战 AI Agent/实战项目/YC平台/`。
> **本仓库只放代码，不放笔记。**

## 当前进度

| Stage | 状态 |
|:-:|---|
| 0 地基与可观测 | 🚧 进行中（Step 4 完成） |
| 1–11 | ⬜ 未开始 |

## 结构

```text
backend/     Python + FastAPI，学习重点
frontend/    Vue，页面交给 AI 生成
```

`backend/src/ycstudio/` 下 14 个模块的职责见 vault 里的《代码目录结构蓝图》。

## 开发

第一次运行先创建本地环境文件，并把示例密码换成本机开发密码；
`POSTGRES_PASSWORD` 和 `DATABASE_URL` 里的密码必须保持一致。

```bash
cp backend/.env.example backend/.env
```

启动和管理 PostgreSQL + pgvector、Redis：

```bash
make up                    # 后台启动 db + redis
make ps                    # 查看健康状态
make db-check              # 验收 SQLAlchemy async session
make logs                  # 持续查看两个服务的日志
make down                  # 停止并删除容器，保留数据卷
```

PostgreSQL 绑定在 `127.0.0.1:5433`，Redis 绑定在
`127.0.0.1:6380`，避免和本机默认端口上的服务冲突。数据保存在 Docker
命名卷中；不要运行 `docker compose down -v`，除非确定要删除本地数据。

Python 开发命令：

```bash
cd backend
uv sync                  # 装依赖
uv run pytest            # 跑测试
uv run ruff check .      # lint
uv run uvicorn ycstudio.main:app --reload   # Step 6 之后可用
```

## Python 版本说明

`requires-python = ">=3.12,<3.14"`。

本机装的是 3.14，但**上限刻意卡在 3.14 以下**：Stage 1 会用到 `torch` / `sentence-transformers`，这类重型 ML 库对新 Python 版本的支持通常滞后半年到一年。

```bash
uv python pin 3.12    # 建议
```

如果想用 3.14，先单独验证 `torch` 和 `sentence-transformers` 能装上再改上限。

## 已知限制

> 项目完成后在这里如实列出。写得出局限才说明真的做过。
