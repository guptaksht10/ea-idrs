# ADR-0003: SQLite for online logging (Phase 3)

- **Status:** Accepted (approved plan: "SQLite logging"). Not used before Nov 17.
- **Date:** 2026-11-06

## Context
The older documents proposed PostgreSQL and Redis. The approved plan says SQLite. The demo
writes at low rates from one process.

## Decision
Use SQLite in WAL mode via SQLAlchemy, with Alembic migrations, when the API is built in
Phase 3. PostgreSQL stays a configuration switch, not a rewrite. No Redis.
The online database never stores ground-truth labels.

## Consequences
Zero operations work. The Nov 17 prototype needs no database: Streamlit calls the library
directly and reads the model bundle from disk.
