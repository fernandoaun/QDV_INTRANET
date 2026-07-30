---
name: local-db-isolation
description: >-
  Keeps the QDV local SQLite database isolated from remote/production Postgres.
  Use when editing .env, DATABASE_URL, instance/, *.db, seed-demo, git add/commit/push,
  deploy, Render, or any talk of syncing local vs remote data.
---

# Local DB isolation (QDV)

## Policy (verbatim)

En local no definas DATABASE_URL en tu .env (así sigue usando SQLite).
No subas nunca .env ni archivos .db.
Podés borrar, cargar demo o romper datos en local sin tocar producción.

## Hard rules

- Local = `project_web/instance/qdv_web.db` (SQLite). Remote = Postgres via `DATABASE_URL` on the host only.
- Never point local `.env` at production/staging Postgres.
- Never `git add` / commit / push: `.env`, `instance/`, `*.db`, `*.db-shm`, `*.db-wal`.
- Never invent a sync, dump/restore, or copy between local SQLite and remote Postgres unless the user explicitly asks and accepts the risk.
- Demo seed (`seed-demo`) is local-only.

## When to warn (stop and alert the user)

Show a clear **ADVERTENCIA** and do not proceed with the risky step if any of these happen:

1. `project_web/.env` defines `DATABASE_URL` (especially `postgres` / remote hosts).
2. Staged or proposed commit includes `.env`, `*.db*`, or `instance/`.
3. Someone asks to “subir la base”, “sincronizar local con remoto”, dump local → Render, or the reverse.
4. A command would run migrations/seed against a non-local `DATABASE_URL`.

Warning template:

```text
ADVERTENCIA — aislamiento de base local
La base local (SQLite) y la remota (Postgres) no se sincronizan.
Riesgo detectado: <qué pasó>.
Acción segura: <qué hacer en su lugar>.
```

## Checks to run

Before commits involving env/db, or when the user asks about local/remote data:

```bash
python .cursor/skills/local-db-isolation/scripts/check_local_db_isolation.py
```

If the script exits non-zero, print its output as the warning and refuse unsafe git/deploy steps until fixed (or the user explicitly overrides).

## Safe defaults

- Leave `DATABASE_URL` unset in local `.env`.
- Keep using `seed-demo` / `CARGAR_DATOS_DEMO.bat` only on local SQLite.
- Push only application code; remote keeps its own database.
