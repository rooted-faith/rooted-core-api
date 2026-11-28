# App support policy: HTTP contract

Stable contract for the minimum supported App build ([ADR 0017](../adr/0017-staging-release-tags-and-app-support-policy.md), ROO-163). The Flutter App (`rooted_flutter`, ROO-165) and the API specification in `rooted-docs` depend on this page. Operator steps live in [docs/operations/app-support-policy.md](../operations/app-support-policy.md).

Field names, error codes, header names, and status codes on this page are a compatibility promise. Old Apps that already show the update screen must keep working, so change them only additively.

## Client identity headers

Policy-aware Apps send both headers on **every** App API request (`/api/...`), signed in or not.

| Header | Value | Example |
| --- | --- | --- |
| `X-App-Platform` | `ios` or `android` | `ios` |
| `X-App-Build` | The installed build number: ASCII digits only, 1–9 of them | `42` |

- Platform is case-insensitive. Surrounding whitespace is ignored in both headers.
- The build is the platform's monotonic integer build number (iOS `CFBundleVersion`, Android `versionCode`), not the marketing version, a date, or a backend tag. It is compared as an integer.
- These headers are a compatibility signal, not authentication. They do not prove which binary sent the request.

## Policy lookup

```
GET /api/v1/app-support/policy?platform=ios
```

- No sign-in. An `Authorization` header is ignored.
- Never gated: works for every build, with or without identity headers, in every enforcement mode.
- The backend environment comes from the server. A client cannot pick it (any `environment` query or header is ignored). Point the App at the staging or production API URL to get that environment's policy.
- Response header `Cache-Control: no-store`.

### 200 OK

```json
{
  "environment": "stg",
  "platform": "ios",
  "minimumBuild": 42,
  "latestBuild": 45,
  "updateUrl": "https://testflight.apple.com/join/AbCdEf",
  "updateInstructions": null,
  "enforcement": "compatible"
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `environment` | string | Server environment: `dev`, `stg`, or `prod` |
| `platform` | `"ios"` \| `"android"` | Echo of the requested platform |
| `minimumBuild` | integer ≥ 0 | Builds **below** this must update. Equal or higher is supported |
| `latestBuild` | integer ≥ `minimumBuild`, or `null` | Newest available build. Informational only: being older than it **never** requires an update |
| `updateUrl` | https URL or `null` | Where to get the replacement build (TestFlight, App Store, Play Store, a download page) |
| `updateInstructions` | string or `null` | Manual update steps, for direct installs with no link. Shown as given (not localized) |
| `enforcement` | `"compatible"` \| `"enforced"` | Whether the request gate rejects requests (see below). For observing the rollout. Clients must not change behavior based on it |

At least one of `updateUrl` and `updateInstructions` is always non-null. The App should still check that `updateUrl` is `https` before opening it.

The client decides: `build < minimumBuild` means show the update screen. Anything else means supported.

### Errors

The usual error envelope (`detail`, `error_code`, optional `context`; dev servers add `debug_detail` and `url`):

| Status | `error_code` | When | App should |
| --- | --- | --- | --- |
| 400 | `APP_IDENTITY_INVALID` | `platform` missing or not `ios`/`android` | Treat it as a bug, not an outdated App |
| 503 | `APP_SUPPORT_POLICY_UNAVAILABLE` | This environment has no valid policy for the platform | Show connection/retry. **Not** the update screen |

Timeouts, 5xx without these codes, and a body that does not match the schema also mean connection/retry, never update-required.

## Request gate

Applies to every route under `/api/` except the policy lookup and the API docs (`/api/docs`, `/api/redoc`, `/api/openapi.json`). It covers anonymous reads and App auth routes (`/api/v1/auth/...`).

Not gated: `/healthz`, everything under `/admin/`, `/webhooks/...`.

Only mobile Apps can pass the gate in enforced mode. A browser client sends no `ios`/`android` identity and is rejected with `400 APP_IDENTITY_INVALID`.

The gate runs before sign-in checks, the request's database session, and any feature code. A rejected request has no side effects.

### Modes

| `enforcement` | Behavior |
| --- | --- |
| `compatible` (default) | Never rejects. Requests without identity, or with any identity, continue as before |
| `enforced` | Rejects as below. Requests with a valid, supported identity continue to normal auth and features |

### Rejections (enforced mode only)

Checked in this order:

| Status | `error_code` | When | `context` |
| --- | --- | --- | --- |
| 400 | `APP_IDENTITY_INVALID` | A header is missing, empty, or malformed; build is negative, has a sign, decimals, or non-ASCII digits, or exceeds 9 digits; platform unknown | none |
| 503 | `APP_SUPPORT_POLICY_UNAVAILABLE` | No valid policy for that platform in this environment | `{"platform": "ios"}` |
| 426 | `APP_UPDATE_REQUIRED` | `build < minimumBuild` | `{"platform": "ios", "build": 40, "minimum_build": 42}` |

Example:

```http
HTTP/1.1 426 Upgrade Required
Content-Type: application/json

{"detail": "This App build is no longer supported. Update the App to continue.", "error_code": "APP_UPDATE_REQUIRED", "context": {"platform": "ios", "build": 40, "minimum_build": 42}}
```

Rules for clients:

- `426` + `APP_UPDATE_REQUIRED` is the only signal for the update screen. Fetch the policy for the update destination. Do **not** refresh tokens, retry, or sign out.
- `426` here means "update the App". It is not an HTTP protocol upgrade, so no `Upgrade` header is sent.
- `426` comes before any auth check. An outdated App with an expired token gets `426`, not `401`.
- `401`/`403` keep their meaning: auth only. They never mean "update required".
- `503` + `APP_SUPPORT_POLICY_UNAVAILABLE` means connection/retry, not update-required.
- CORS headers are present on rejections.

## Handoff

**`rooted_flutter` (ROO-165)**

- Send `X-App-Platform` and `X-App-Build` from the shared API client on every request, including before sign-in.
- On startup and on return to the foreground, call the policy lookup and compare `build < minimumBuild`.
- Handle `426 APP_UPDATE_REQUIRED` in one central place, using the same update screen.
- Treat `503 APP_SUPPORT_POLICY_UNAVAILABLE`, timeouts, and malformed bodies as connection/retry.

**`rooted-docs`**

- Copy this endpoint, the headers, the schema, and the three error codes into `docs/backend/api-specification.md`.
- This ticket does not edit that repository.
