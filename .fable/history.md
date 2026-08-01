# Stage 0 Step 4 — SQLAlchemy async foundation

## Goal

Build and verify the production database foundation without pulling Step 6 FastAPI
application assembly forward.

## Acceptance criteria

- `DeclarativeBase`, `AsyncEngine`, `async_sessionmaker`, and `get_session` exist in `db/`.
- Pool configuration comes from Settings and `pool_pre_ping` is enabled.
- Commit policy is explicit: services commit; the dependency rolls back failures and closes.
- A real PostgreSQL probe passes `SELECT 1`.
- Ten concurrent tasks use independent sessions without pool exhaustion.
- Explicit commit persists, while 50 injected failures roll back and do not leak connections.
- Probe artifacts are removed from PostgreSQL after the run.
- Relevant docs and progress markers match observed evidence.

## Requirements (append-only)

1. Follow Stage 0 Step 4 in the implementation manual.
2. Explain where code belongs and which terminal commands reproduce the checks.
3. Use SQLAlchemy 2.0 async patterns compatible with the locked dependencies.
4. Do not create the complete FastAPI app before Step 6.
5. Add new questions and conclusions to the Stage 0 Step 4 question note.

## Decision log

- 2026-08-01: Use service-level explicit commit; `get_session` owns rollback and close only.
- 2026-08-01: Use a repeatable CLI probe instead of a temporary HTTP route because the app
  assembly is intentionally scheduled for Step 6.
- 2026-08-01: Configure a five-connection base pool plus five overflow connections so the
  ten-task acceptance check has an explicit, understandable limit.

## Evidence

- `ruff format --check .`: 32 files formatted.
- `ruff check .`: all checks passed.
- `mypy src`: no issues in 27 source files.
- Step 4 probe: temporary `SELECT 1` route passed.
- Step 4 probe: 10 concurrent requests passed with independent sessions.
- Step 4 probe: explicit commit persisted; 50 injected request failures rolled back.
- PostgreSQL `to_regclass` check confirmed the probe table was removed.
