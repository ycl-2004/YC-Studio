# YC Studio

用户上传知识库驱动的内容生成工作台。

上传参考资料建成四层分库 → 跟 Agent 聊出结构化选题卡 → 6 节点工作流生成文章 → 两处人审 → 导出 → 回填效果数据 → 高表现内容回流成新案例。

> 设计文档、实施手册与决策记录全部在 Obsidian vault 的
> `学习资料/百战 AI Agent/实战项目/YC平台/`。
> **本仓库只放代码，不放笔记。**

## 当前进度

| Stage | 状态 |
|:-:|---|
| 0 地基与可观测 | 🚧 进行中（Step 2 完成） |
| 1–11 | ⬜ 未开始 |

## 结构

```text
backend/     Python + FastAPI，学习重点
frontend/    Vue，页面交给 AI 生成
```

`backend/src/ycstudio/` 下 14 个模块的职责见 vault 里的《代码目录结构蓝图》。

## 开发

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
