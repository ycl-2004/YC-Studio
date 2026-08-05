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
| 0 地基与可观测 | ✅ Step 1–11 完成 |
| 1 知识库摄取与四层分库 | ✅ Step 1–12 完成，6 条完成判据全部验收（前后端已接通） |
| 2 评测体系 | ✅ 8 个 Step 完成；真实 80-case HTTP/ARQ baseline 已记录 |
| 3–11 | ⬜ 未开始 |

Stage 1 交付：10 个 `/api/kb/*` 端点、108 项后端测试、四层分库摄取与检索、
知识库管理页（上传 / 列表 / 预览原文与原件 / 检索 / 删除）。

Stage 2 实现：4 张 `eval_*` 表（Alembic `0007`）、Recall@k / MRR / NDCG、
五类失败归因、可复现配置快照、ARQ 异步 runner、run 对比 API 与检索评测页。
真实数据已通过 HTTP 上传三份项目手册，得到 64 searchable chunks；DeepSeek HTTP 生成
60 条 synthetic，再补 20 条 manual，形成 80 条 active cases。两次 ARQ baseline 均为
80/80 completed、0 failed，Recall@5=0.9300、MRR=0.7373、NDCG@5=0.7858；P95 分别为
63.61ms 和 55.67ms。归因 count 两次完全一致：hit 43、low_rank 5、ambiguous 26、
not_in_kb 0、not_recalled 6。完整 run id、配置快照和 compare 证据见 vault 的《Stage 2
评测体系》记录。

## 结构

```text
backend/     Python + FastAPI，学习重点
frontend/    Vue 3 + Vite 工作台（知识库页连真实 API，其余四页仍是 mock）
```

`backend/app/` 下模块的职责见 vault 里的《代码目录结构蓝图》。Stage 2 评测实现位于
`backend/app/evaluation/`，数据模型位于 `backend/app/db/models/evaluation.py`。

## 启动

第一次运行先创建本地环境文件，并把示例密码换成本机开发密码；
`POSTGRES_PASSWORD` 和 `DATABASE_URL` 里的密码必须保持一致。

```bash
cp backend/.env.example backend/.env
```

前后端**一起启动**有两种方式，选一种即可，两种都不需要手动分别开进程：

| 命令 | 跑在哪 | 什么时候用 |
|---|---|---|
| `make up` | 五个服务全在 Docker | 演示、验收、接近生产的验证 |
| `make dev` | db/redis 在 Docker，backend + worker + frontend 在宿主机热重载 | 日常写代码 |

```bash
make up      # → http://127.0.0.1:5173  前端已连真实 API
make dev     # → http://127.0.0.1:5173 + http://127.0.0.1:8000，Ctrl-C 一次全停
make help    # 全部命令
```

两种模式**不能同时开**：它们抢同样的宿主机端口和同一个数据库。`make dev` 会先自动
停掉容器里的 backend / worker / frontend，只保留 db 和 redis，所以直接切换即可；
要切回容器模式再运行一次 `make up`。

`make dev` 里 worker 也跑在宿主机，而不是留用容器里那个：批量上传把原始文件写进
`backend/data/uploads/`，容器 worker 只能看到 `upload_data` 卷，混用会让排队的文件全部
以「文件不存在」失败。

其他常用命令：

```bash
make ps                    # 五个服务的状态
make logs                  # 持续查看日志
make down                  # 停止并删除容器，保留数据卷
make db-check              # 验收 SQLAlchemy async session
make health-check          # 验收 /health、/ready 与数据库故障恢复
make dev-frontend          # 只跑前端，走 mock，完全不需要后端
```

Compose 按依赖顺序启动：PostgreSQL / Redis healthy → backend healthy → frontend。
也可以直接运行 `docker compose --env-file backend/.env up --build` 在前台查看启动过程。
Backend 启动前会自动执行 `alembic upgrade head`。

### 真实 API 与 mock 的切换

前端的数据来源由 `VITE_USE_MOCK` 决定，在 `frontend/src/api/client.js` 读取：

| 场景 | 取值 | 效果 |
|---|---|---|
| `make up`（容器） | compose 构建参数传 `false` | 知识库页连真实 API |
| `make dev`（本地） | 目标里传 `false` | 同上 |
| `make dev-frontend` | 未设置，默认 mock | 五个页面全用浏览器内假数据 |

它是 Vite 的构建期变量，**容器模式下改了要重新 `make up` 构建镜像**，重启容器不生效。
要让容器全栈退回 mock 演示，在 `backend/.env` 里加 `VITE_USE_MOCK=1` 再 `make up`。

无论开关怎么设，输出配置 / 生成工作台 / 内容库 / 复盘看板四个页面都仍是 mock——
它们的 `frontend/src/api/*.js` 里还没有任何真实请求，后端也还没有对应路由。

### 两个容易踩的前置条件

- **模型缓存**：`EMBEDDING_LOCAL_FILES_ONLY=true` 时镜像不会联网下载模型，镜像本身也不带。
  compose 把宿主机的 `~/.cache/huggingface` 挂进 backend 和 worker，所以本机必须先有
  `BAAI/bge-base-zh-v1.5`；否则案例库 / 素材库的摄取会以 `LocalEntryNotFoundError` 失败，
  而规则库 / 模板库因为不做 embedding 反而正常，很容易误判。缓存在别处用
  `HF_CACHE_DIR` 覆盖。
- **前端容器的 `/api`**：由 nginx 反代到 backend，配置在 `frontend/nginx.conf`。它用变量
  形式的 `proxy_pass` 让 DNS 在请求时解析，否则 backend 容器一重启换了 IP，nginx 会一直
  打旧地址返回 502，直到 nginx 自己重启。

已有开发数据卷在拉取到新 migration 后，运行 `make up` 会重建 backend 镜像并在启动时自动升级到
Alembic head。先用下面的命令确认当前 revision；重要数据应在 schema 更新前自行备份：

```bash
docker compose --env-file backend/.env exec backend alembic current
```

migration 会先创建检索索引。数据库批量导入真实 chunks 后，再运行一次索引重建与延迟基线测试，
让 HNSW 图基于真实向量生成：

```bash
docker compose --env-file backend/.env exec backend python scripts/build_indexes.py
```

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
uv sync                  # 装依赖（等价于 make sync）
uv run pytest            # 跑测试（等价于 make test）
uv run ruff check .      # lint
```

只想单独跑 backend（不带前端）用 `make dev-backend`；只想跑依赖容器用 `make infra-up`。

## 以后加一个新接口，要动哪几个文件

Stage 2+ 每加一个能力都会重复这条路径。以知识库为模板：**后端三处、前端两处**。

### 后端

```text
1. app/schemas/<域>.py     Pydantic request/response 模型 —— 先冻结契约再写别的
2. app/services/<域>.py    业务逻辑，只收 session 和普通参数，不碰 FastAPI 对象
                           错误用领域异常表达（SourceNotFoundError 之类）
3. app/api/<域>.py         路由：解析入参 → 调 service → 把领域异常映射成 HTTP 状态码
                           新文件要在 app/api/__init__.py 的 api_router 里 include
```

分层的意义在于**错误映射**：service 抛 `SourceNotFoundError`，路由把它翻成 404；
service 完全不知道 HTTP 存在，所以能被 worker、CLI、测试直接复用。

### 前端

```text
4. frontend/src/api/<域>.js   加函数，内部两条路径：
                              if (!USE_MOCK) { …真实 request… } else { …mock… }
                              字段规范化也放这一层
5. frontend/src/pages/*.vue   页面只调 api 层，不关心数据来自哪边
```

### 规范化必须在 api 层做

把 `VITE_USE_MOCK` 翻成 `false` 时暴露的不是「连不上」，而是 mock 当初随手定的字段名
从来没人校对过。知识库这次要处理四类差异：

| 差异 | mock | 后端真实 | 处理 |
|---|---|---|---|
| 列表包装 | `{items, total}` | `{collections}` / `{sources}` | api 层统一成 `{items, total}` |
| 摄取状态 | 三态 | `IngestStatus` 六态 | 六态折叠成表格要的三态 |
| 文件大小 | mock 自带 | 列表接口没这个字段 | 列表显示「—」，大小从预览接口取 |
| 检索入参 | 只要 `collectionId` | 必须带 `kind` | 页面把当前库的 kind 传下去 |

规范化写在 api 层，页面组件就永远不需要 `if (mock)`——这也是为什么四个还没接后端的页面
可以原样留着 mock，不影响已接通的知识库页。

### 加完的自检

```bash
cd backend && uv run pytest && uv run ruff check . && uv run mypy app
cd ../frontend && npm run build
make up      # 在容器里真打一次请求，别只信测试
```

最后一步不能省。Stage 1 里「测试全绿但跑不起来」这条学费交了三次：最后一次是 108 个
后端测试全过、五个容器全 healthy，真去页面点上传照样 500——镜像里既没有 embedding 模型，
也没有 `libxcb`。**测试验的是代码，不是环境。**

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

Stage 1 的接口包括同步单文件摄取 `POST /api/kb/upload`、异步批量摄取
`POST /api/kb/batch-upload`（通过 ARQ worker 逐个处理）及其进度查询
`GET /api/kb/batches/{batch_id}`、检索 `POST /api/kb/search`。为支持 Step 12
知识库管理页，另补充了库与文档的枚举/删除能力：`GET /api/kb/collections`
（列举可见库，可选 `?kind=` 过滤，带实时 source/document/chunk 计数）、
`POST /api/kb/collections`（创建当前用户私有库）、`GET /api/kb/collections/{id}`
（单库元数据）、`GET /api/kb/collections/{id}/sources`（列举该库文档与 ingest 状态）、
`DELETE /api/kb/sources/{source_id}`（软删文档 + 级联清 chunk）、
`DELETE /api/kb/collections/{id}`（删私有库，级联清全部数据）。Step 12 又补了两个供管理页
查看内容用的只读接口：`GET /api/kb/sources/{id}/preview`（文件信息 + 解析原文 `raw_text` +
有序切片，两处文本都有长度上限并带截断标志）、`GET /api/kb/sources/{id}/file`
（按后缀决定 Content-Type 流式返回原始字节；HTML 一律降级为 `text/plain` 且强制
attachment，全响应带 `nosniff`）。当前都以 `X-User-ID`
作为临时身份边界来执行私有库权限；Stage 4 会将其替换为已验证的登录身份。

公共规则库与模板库位于 `backend/seeds/rules/`、`backend/seeds/templates/`，可通过
`make seed-public` 初始化或同步。它按 `(库类型, 相对 Markdown 路径, 内容 hash)` 幂等：不变内容
跳过，变更文件只重建自身的派生 document/chunk。容器默认不执行；设置
`SEED_PUBLIC_LIBRARIES=1` 后，backend 会在迁移完成、启动服务前同步一次。公共库不接受上传 API 写入。

## Python 版本说明

`requires-python = ">=3.12,<3.14"`。

本机装的是 3.14，但**上限刻意卡在 3.14 以下**：Stage 1 会用到 `torch` / `sentence-transformers`，这类重型 ML 库对新 Python 版本的支持通常滞后半年到一年。

```bash
uv python pin 3.12    # 建议
```

如果想用 3.14，先单独验证 `torch` 和 `sentence-transformers` 能装上再改上限。

## 已知限制

> 项目完成后在这里如实列出。写得出局限才说明真的做过。

Stage 1 收尾时如实记录的限制与待改进项：

**身份与安全**

- `X-User-ID` 是临时身份边界，任何人伪造这个头就是任何人。Stage 4 换成登录身份时，
  文件下载接口（`/sources/{id}/file`）的鉴权要重做——现在猜到 `source_id` 就能下载原件。
- 上传没有速率限制，也没有单用户配额。

**存储与规模**

- 原始文件只存本地磁盘（`LocalUploadStorage`）。多副本部署要换对象存储；
  接口形状已经隔离在 adapter 层，换的时候不该动到 service。
- 软删除的 source 会一直占着 `(collection_id, content_hash)` 这个唯一键，
  没有清理任务；长期运行需要一个归档策略。
- 预览接口一次返回全部切片（上限 200 条）。切片过千的文档需要分页或懒加载。

**摄取**

- 换 embedding 模型没有重建流程。改了 `EMBEDDING_MODEL` 之后旧向量与新模型不在同一空间，
  检索会**静默变差**而不是报错，必须全量重新 embedding。
- worker 重启后的恢复逻辑只做过代码审计，**没有自动化测试**。
- 批量上传的进度只有计数，没有单个文件的失败原因汇总（要去查 `Source.error_message`）。
- 扫描版 PDF 只报「无文本层」错误，没有接 OCR。

**前端**

- 只有知识库页连了真实 API，其余四页是 mock。
- 上传抽屉走的是逐个同步上传，还没接批量路由（后端已就绪）。
- DOCX 只能下载不能预览。
- 页面没有做移动端适配，也没有做 i18n。
