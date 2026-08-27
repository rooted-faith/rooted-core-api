# ADR 0002 — API responses use camelCase JSON without a data wrapper

## Status

Accepted (Phase 0, 2026-08-27)

## Context

The Flutter/PWA client and `rooted-docs/docs/backend/api-specification.md` require a stable JSON contract for v1. The legacy portal stack often used snake_case or wrapped payloads inconsistent with the NewLife admin/app clients we are aligning with.

Rooted end-user APIs must be easy to consume from Dart/TypeScript clients and documented in one place.

## Decision

1. **Success responses** serialize with **camelCase** property names in JSON.
2. **No** generic wrapper such as `{ "data": { ... } }` for successful single-resource or list responses — the resource object (or pagination object) is the top-level JSON body.
3. **Pagination** uses a flat object: `items`, `page`, `pageSize`, `total`, `totalPages` (camelCase in wire format).
4. **Internal models** remain Python `snake_case` (commands, results, domain, request bodies). Response serializers use Pydantic `serialization_alias` (or equivalent) for camelCase output.
5. **Request bodies and query parameters** accept snake_case from clients where documented; prefer consistency with `newlife-core-api` mapper patterns.
6. **Errors** follow the API spec shape (e.g. structured `detail` with `message` and `errorCode` where applicable); exception handlers must not reintroduce a success-style `data` wrapper.

## Consequences

- All new serializers for app API (`/api/v1`) and admin API must implement the alias pattern before merge.
- OpenAPI generated from FastAPI should reflect camelCase on responses (field aliases / schema customization as needed).
- Tests should assert JSON keys in camelCase for HTTP-level contract tests.
- Deviations require a new ADR and an update to `rooted-docs` API specification.
