# ADR 0001 — Adopt NewLife Core API architecture template

## Status

Accepted (Phase 0, 2026-08-27)

## Context

`rooted-core-api` began as a fork of the portal-style FastAPI codebase (`rooted-portal-api`) with handlers, a single container, and an admin sub-app mount. Rooted v1 needs predictable boundaries for **devotion**, **bible**, **journal**, and **fellowship**, plus shared auth/RBAC — similar complexity to `newlife-core-api`, but **without** facility booking, org/ministry modules, or Microsoft OIDC.

Maintaining a one-off structure would duplicate lessons already captured in NewLife’s clean architecture (domain → application → infrastructure → delivery) and slow agent/human onboarding.

## Decision

Adopt the **NewLife Core API architecture template** as the target for all new and migrated code:

- Layers: `portal/domain/`, `portal/application/`, `portal/infrastructure/`, delivery (`routers`, `serializers`, `middlewares`), `portal/models/` for ORM only
- Dependency rules and mapper boundary as documented in `AGENTS.md` (aligned with `newlife-core-api/AGENTS.md`)
- Composition root evolves toward nested containers (`core`, `admin`, context-specific containers) rather than growing a flat handler tree
- **Bounded contexts for Rooted product code:** `devotion`, `bible`, `journal`, `fellowship`, plus platform `auth`, `users`, `sync`, `reports`, `rbac`, `audit`
- **Explicitly not ported:** `facility`, `org`, `ministry`, Microsoft Entra auth services

Legacy `portal/handlers/` may remain temporarily (e.g. bible import/read); new features must not add handlers except thin CLI bridges.

## Consequences

- Phase 0+ refactors move vertical slices into application services incrementally; dual patterns coexist until migration completes.
- Agents and contributors use `AGENTS.md` + this ADR as the north star; `docs/ARCHITECTURE.md` describes runtime layout and may lag until rewritten post-migration.
- Shared patterns (JWT, RBAC, Ruff, uv, Alembic policy) stay aligned with NewLife for easier cross-repo maintenance.
- Repository rename to `rooted-core-api` reflects “core product backend”, not a generic portal-only service.
