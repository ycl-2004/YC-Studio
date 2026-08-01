# Stage 0 Step 5 — Alembic initialization and first migration

## Goal

Make PostgreSQL schema changes reproducible and reversible with an async Alembic environment,
an initial `users` model, and a separately reviewed pgvector extension migration.

## Acceptance criteria

- Alembic uses the official async template and the locked `asyncpg` database URL.
- `env.py` loads `Settings`, imports project models, and exposes `Base.metadata`.
- The first `User` model is minimal, typed with SQLAlchemy 2.0, and registered in metadata.
- A hand-written revision enables the PostgreSQL `vector` extension.
- A reviewed autogenerate revision creates `users` and cleanly drops it on downgrade.
- `alembic upgrade head`, `downgrade -1`, and re-upgrade all succeed against the real database.
- The `vector` extension and final users schema are verified from PostgreSQL.
- Formatting, lint, typing, and existing database regression checks pass.
- Step 5 docs reflect only observed evidence.

## Requirements (append-only)

1. Follow Stage 0 Step 5 in the implementation manual and the project architecture docs.
2. Use Alembic 1.18.5, SQLAlchemy 2.0.51, and asyncpg 0.31.0 locked by `uv.lock`.
3. Keep the initial user schema minimal; do not implement authentication early.
4. Keep pgvector extension creation in a hand-written migration because autogenerate cannot infer it.
5. Human-review generated migration content before applying it.
6. Do not commit, stage, push, or modify Docker drafts.
7. Update the Step 5 learning note and implementation checklist with actual results.
8. Add a realistic repeatable script check for migration head, schema, rollback-safe ORM I/O,
   uniqueness enforcement, and zero persisted probe rows.

## Decision log

- 2026-08-01: Use two linear revisions: vector extension first, users table second.
- 2026-08-01: Use UUID user IDs so every later `user_id` foreign key is ready for the planned
  single-user-now, extensible-later architecture.
- 2026-08-01: Limit the first users table to identity and audit fields; authentication fields
  belong to the later authentication stage.

## Evidence

- Official async Alembic 1.18.5 template initialized under `backend/migrations`.
- `0001` applied successfully and idempotently enabled/registered pgvector.
- Autogenerate reported only `Detected added table 'users'`; `0002` was manually reviewed.
- First `upgrade head` created the expected UUID/email/timestamptz users schema at revision 0002.
- `downgrade -1` removed users, returned to 0001, and preserved vector 0.8.2.
- Re-upgrade restored revision 0002 and `alembic check` found no new operations.
- `ruff format --check .`: 36 files formatted; `ruff check .`: passed.
- `mypy src`: passed for 28 source files.
- Existing async database probe passed all four checks and removed its probe table.
- `make migration-check` passed revision/head, vector, reflected schema, rollback-safe ORM
  round-trip, duplicate-email enforcement, and zero-residue checks.
- The migration check script passed its focused Ruff and mypy checks.
- `pytest`: zero tests collected (exit 5); the test skeleton remains scheduled for Step 9.
- Outstanding by user instruction: migrations are uncommitted, so the version-control checkbox
  remains open until the user creates the Step 5 commit.
