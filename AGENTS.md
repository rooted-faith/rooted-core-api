# AGENTS.md — AI Entry Guide for rooted-core-api

This document helps AI agents quickly understand the **Rooted Core API** codebase: architecture direction, domain boundaries, conventions, and where to make changes. For diagrams and extended narrative, see [`README.md`](README.md) and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). For enforceable coding rules, see [`.cursor/rules/standard.mdc`](.cursor/rules/standard.mdc). For product language, see [`CONTEXT.md`](CONTEXT.md).

---

## 1. What This Project Is

| Item                | Value                                                                                                      |
| ------------------- | ---------------------------------------------------------------------------------------------------------- |
| **Purpose**         | Backend for **Rooted（扎根）** — personal devotion, private journal, and small-group fellowship (4–15 people) |
| **Framework**       | FastAPI (async)                                                                                            |
| **Database**        | PostgreSQL + SQLAlchemy (asyncpg)                                                                          |
| **Cache**           | Redis (sessions, rate limiting, auth blacklist when enabled)                                               |
| **Auth (app)**      | JWT — passwordless magic link for End users (see ADR 0003); Identity link storage ADR 0005; End-user Apple/Google HTTP still future |
| **Auth (admin)**    | JWT + RBAC — email/password and Google ID-token (ADR 0006); **no** Microsoft Entra / Admin Apple            |
| **DI**              | `dependency-injector`                                                                                      |
| **Package manager** | uv (`uv run …`)                                                                                            |
| **Python**          | 3.14+ (see `pyproject.toml`)                                                                               |
| **Migrations**      | Alembic — **agents must not add/modify/delete files under `alembic/versions/`**                            |

### Related repositories

| Repo           | Role                                                        |
| -------------- | ----------------------------------------------------------- |
| `rooted_app`   | Mobile web / PWA client (Flutter or web — see rooted-docs)  |
| `rooted-docs`  | PRD, API spec, database design, product docs                  |

### Architecture status

Adopts **newlife-core-api** Clean Architecture (ADR 0001): `RootContainer`, three ASGI mounts (`portal/apps.py`), platform modules under `portal/application/`. **Bible** is the first completed vertical slice (`application/bible/`). Legacy `portal/handlers/` is removed.

**Out of scope for Rooted:** facility booking, org/ministry ERP, Microsoft SSO.

---

## 2. Quick Commands

```bash
# Install
uv sync

# Local infra (if docker compose present)
docker compose up -d

# DB migrate
uv run alembic upgrade head

# Dev server
uv run uvicorn portal.main:app --reload
# or: uv run python -m portal

# Tests
uv run pytest

# Bible data CLI (content ops)
uv run python -m portal.cli.main import-bible --bible-id 1392
uv run python -m portal.cli.main dump-bible --bible-id 1392 --out dump

# Format (layout, then import sort — I only)
uv run ruff format
uv run ruff check --fix
```

Copy `example.env` → `.env` before running locally.

| URL                                      | Description                          |
| ---------------------------------------- | ------------------------------------ |
| `http://127.0.0.1:8000/healthz`          | Public health check                  |
| `http://127.0.0.1:8000/api/v1/...`       | End-user app API                     |
| `http://127.0.0.1:8000/admin/api/v1/...` | Admin API (authenticated + RBAC)     |
| `http://127.0.0.1:8000/docs`             | OpenAPI                              |

Spec reference: `rooted-docs/docs/backend/api-specification.md`.

---

## 3. Architecture (Clean Architecture — target)

**Rule of thumb:** dependencies point **inward**. Delivery and infrastructure depend on application and domain — never the reverse.

```
HTTP Request
  → Middleware (auth, session, locale)
  → Router (delivery)
  → Mapper: Serializer → Command
  → Service (application)
  → Port (domain Protocol)
  → Repository / Cache (infrastructure)
  → PostgreSQL / Redis
  → Result → Mapper → Serializer → JSON (camelCase, no data wrapper)
```

### Layer map (target)

| Layer              | Path                                                            | Owns                                         |
| ------------------ | --------------------------------------------------------------- | -------------------------------------------- |
| **Domain**         | `portal/domain/`                                                | `entities.py`, `ports.py`, `constants.py`    |
| **Application**    | `portal/application/`                                           | `*_service.py`, `commands.py`, `results.py`, `mappers.py` |
| **Infrastructure** | `portal/infrastructure/`                                        | `persistence/repositories/`, `cache/`        |
| **Delivery**       | `portal/routers/`, `portal/serializers/`, `portal/middlewares/` | HTTP, API contracts                          |
| **ORM**            | `portal/models/`                                                | SQLAlchemy models only                       |
| **DI**             | `portal/containers/`, `portal/container.py`                     | `RootContainer` + core/admin/app/events |
| **CLI**            | `portal/cli/`                                                   | Click entrypoints; seed logic in `application/cli/` |

### Hard dependency rules

1. `routers` → `application` (services) → `domain`
2. Application **must not** import `portal.serializers` (exception: `application/*/mappers.py`)
3. Application **must not** import `portal.models`
4. Repositories map to **domain entities** or **application results** — never response serializers
5. Infrastructure satisfies domain **Ports** via structural typing

---

## 4. Application Entry & HTTP Layout

### ASGI mount structure (`portal/apps.py`)

```
FastAPI (public)  portal.main:app
├── GET /healthz
├── mount /admin  →  /admin/api/v1/...  (AuthMiddleware + RBAC)
└── mount /api    →  /api/v1/...        (member API)
```

- **App API prefix:** `/api/v1` (auth, devotion, journal, fellowship, bible, sync, reports — see spec)
- **Admin API prefix:** `/admin/api/v1` (content moderation, RBAC, catalog ops)

---

## 5. Bounded Contexts & Services

Rooted v1 domains (from PRD and `rooted-docs`). Use these folder names when adding code.

### Product domains

| Context        | Responsibility                                                                 | API prefix (app)        |
| -------------- | ------------------------------------------------------------------------------ | ----------------------- |
| **devotion**   | Daily lesson flow, series/plans, Amen (`WalkDay`), lesson notes tied to devotion | `/api/v1/devotion`      |
| **bible**      | Licensed/public-domain text, versions, passages, bookmarks                     | `/api/v1/bible`         |
| **journal**    | Private journal entries, personal prayers, memory cards — **never** group-visible | `/api/v1/journal`   |
| **fellowship** | Groups, covenant, prayer wall, encouragements, shares (no v1 DMs)              | `/api/v1/groups`, `/fellowship` |

### Platform

| Context    | Responsibility                                      |
| ---------- | --------------------------------------------------- |
| **auth**   | Magic-link End-user auth; Admin password + Google (ADR 0006); refresh, JWT; Identity links (ADR 0005) |
| **users**  | Profile, preferences, account deletion              |
| **sync**   | Client ↔ server sync for v1                         |
| **reports**| User reports + moderation queue                     |
| **rbac**   | Admin roles/permissions/resources                   |
| **audit**  | Admin User audit trail where required               |

### Privacy invariant (journal)

`journal_entries`, `personal_prayers`, and private `lesson_notes` **must not** appear in fellowship queries, group analytics, or exports. See `CONTEXT.md` and PRD §12.

### ORM / schema hints

Follow `rooted-docs/docs/backend/database-design.md` for table groupings (`bible_*`, devotion content, journal, fellowship).

---

## 6. Dependency Injection

**Composition root:** `portal/container.py` → `RootContainer` with `core`, `admin`, `app`, `events`.

- Member bible: `Container.bible_service` via `AppContainer`
- Admin platform: auth, rbac, locale, content via `AdminContainer`
- Routers: `@inject` + `Depends(Provide[Container.<service>])`

---

## 7. Request / Response Conventions

See ADR 0002 and `rooted-docs/docs/backend/api-specification.md`.

### Pydantic field naming

| Layer                             | Field style             | `serialization_alias`          |
| --------------------------------- | ----------------------- | ------------------------------ |
| Commands / Results / Domain       | `snake_case`            | No                             |
| Request serializers (body, query) | `snake_case`            | No                             |
| Response serializers (API output) | `snake_case` internally | **Yes** — `camelCase` for JSON |

- **No** `{ "data": { … } }` success wrapper.
- Pagination shape: `{ items, page, pageSize, total, totalPages }` in camelCase JSON.
- Clients may send snake_case query/body; responses are camelCase.

### Mappers (`application/*/mappers.py`)

The **only** application files allowed to import `portal.serializers`.

```text
to_command(serializer)  → Command
to_api(result)        → Response serializer
```

---

## 8. Auth & Authorization

See ADR 0003.

### App users

- **Passwordless:** magic-link request/verify for End users (ADR 0003). Auth credentials may have `password_hash` null.
- Shared JWT access/refresh infrastructure with Admin; product FKs hang off End user (`app.user`), not `auth.user` alone (ADR 0004).
- Identity provider catalog + Identity link rows (ADR 0005). **Admin Google** ID-token HTTP is ADR 0006. End-user Apple/Google HTTP remains a future ADR.
- **Excluded:** Microsoft Entra ID token exchange, Admin Apple, app password register/login as the product path, phone-as-login-id.

### Admin

1. `AuthMiddleware` validates Bearer JWT and loads admin user.
2. RBAC via permissions on admin routes (see `portal.libs.consts.permission` pattern).
3. Admin create/login: **email + password** and/or **Google** on the shared Auth credential (ADR 0006).

### Auth levels (product)

| Level    | Access                                                |
| -------- | ----------------------------------------------------- |
| Anonymous| Read devotion/bible where spec allows (client-first)|
| Member   | Sync, journal, fellowship                             |
| Shepherd | Group pastoral views per membership.role              |

---

## 9. Infrastructure Patterns

### Repositories (target)

- Constructor: `__init__(self, session: Session)`
- Reads/writes via async session helpers in `portal/libs/database/`
- Filter soft-deleted rows unless explicitly listing deleted

### Tracing

Use `@distributed_trace()` from `portal.libs.tracing.distributed_trace` on application services.

### Database session

- Request-scoped session via `CoreRequestMiddleware`
- **Do not** edit `alembic/versions/` — human-managed migrations

### File storage

AWS S3 via configured providers when uploading user or content media (see config / existing providers).

---

## 10. Testing

```
tests/
├── conftest.py
├── application/          # mirror portal/application/
│   └── bible/
└── test_*.py
```

- `pytest` + `pytest-asyncio` + `pytest-mock`
- Async tests: `@pytest.mark.asyncio`
- Run: `uv run pytest`
- Mirror `portal/application/` under `tests/application/` as clean architecture lands

---

## 11. Adding a Feature (Vertical Slice Checklist)

1. **Domain** — `portal/domain/<ctx>/` entities + ports
2. **Application** — commands, results, service, mappers
3. **Infrastructure** — repositories (+ cache if needed)
4. **ORM** — `portal/models/` + human migration
5. **Delivery** — serializers under versioned folders, routers under `portal/routers/apis/v1/` or admin
6. **DI** — register in container
7. **Tests** — application service tests with stub repos
8. **Docs** — update `rooted-docs` API spec when contract changes

Pick **`application/bible/`** as the reference vertical slice for new domains.

---

## 12. Naming Conventions

| Kind                        | Convention            | Example                |
| --------------------------- | --------------------- | ---------------------- |
| Variables, functions, files | `snake_case`          | `passage_service.py`   |
| Classes                     | `PascalCase`          | `PassageService`       |
| Constants, env vars         | `UPPER_SNAKE_CASE`    | `JWT_SECRET_KEY`       |
| Comments                    | English only          |                        |

---

## 13. Do NOT (Agent Guardrails)

| Action                                           | Reason                                        |
| ------------------------------------------------ | --------------------------------------------- |
| Add/modify/delete `alembic/versions/**`          | Project policy                                |
| Import `portal.models` in application services   | Clean Architecture boundary                   |
| Import `portal.serializers` outside `mappers.py`   | Boundary violation                            |
| Expose journal/private note content to fellowship| Product privacy (PRD)                         |
| Add facility, org/ministry, or Microsoft OIDC      | Wrong product — use newlife-core-api          |
| Run `git commit/push/merge` unless user asks     | Automation policy                             |
| Use black/isort/flake8                           | Use Ruff (`uv run ruff format`, `ruff check --fix`) |

---

## 14. Key Files Index

| File                               | Why read it                          |
| ---------------------------------- | ------------------------------------ |
| `CONTEXT.md`                       | Ubiquitous language                  |
| `docs/adr/`                        | Architecture and API decisions       |
| `README.md`                        | Setup                                |
| `.cursor/rules/standard.mdc`       | Coding standards                     |
| `pyproject.toml`                   | uv + Ruff                            |
| `portal/apps/__init__.py`          | ASGI mounts, middleware stacks       |
| `portal/containers/`               | RootContainer sub-containers         |
| `portal/application/bible/`        | Reference vertical slice             |
| `portal/routers/apis/v1/bible.py`  | Bible HTTP delivery                  |
| `portal/serializers/apis/v1/bible.py` | camelCase API models              |
| `example.env`                      | Required env vars                    |

---

## 15. Mental Model for AI Agents

| Task type              | Start here                                              |
| ---------------------- | ------------------------------------------------------- |
| New app endpoint       | `rooted-docs` API spec → router → service → repo → model |
| Bible API / reader     | `application/bible/` → `infrastructure/.../bible_repository.py` |
| Bible content pipeline | `portal/cli/` import/dump commands                              |
| Privacy bug            | Trace fellowship queries — journal tables must be absent |
| API JSON shape         | Serializers + ADR 0002                                   |
| Auth                   | JWT providers, `AuthMiddleware`, ADR 0003                 |
| Admin RBAC             | Admin sub-app routers + permission constants            |

**Prefer minimal diffs.** Match patterns in the same bounded context.

---

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues (via `gh`). See `docs/agents/issue-tracker.md`.

### Triage labels

See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `CONTEXT.md` + `docs/adr/`. See `docs/agents/domain.md`.
