# ADR 0006 — Admin Google ID-token sign-in (Identity link HTTP flow)

## Status

Accepted (2026-09-05)

Authorizes the first Identity-provider HTTP flow on top of ADR 0005 storage. Amends ADR 0003’s “admin password only / no OIDC” clause for **Google on the admin console only**. Does **not** authorize End-user Google/Apple app flows (future ADR) or Microsoft Entra.

## Context

ADR 0005 delivered `identity_provider` / `identity_link` and seeded `google` + `apple`, but left OAuth/OIDC HTTP flows to a later decision. Product still schedules End-user Apple/Google for a later app phase; staff asked to enable **Google sign-in on the Rooted admin portal** first, while keeping password login and without public Admin self-registration.

Google issues a stable account `sub` across OAuth clients (Web / iOS / Android). Rooted’s link uniqueness is `(provider, provider_tenant, provider_subject)` — one Google subject maps to one Auth credential, not one link per Client ID. Client IDs still matter for ID-token `aud` verification.

## Decision

1. **Surface (this slice):** Admin console + `/admin/api/v1/auth` only. End-user `/api/v1` Google/Apple remain unauthorized here.

2. **Protocol:** Portal uses Google Identity Services (or equivalent) to obtain a Google **ID token** and posts it to the admin API. The API verifies signature/`iss`/`exp`, requires `email_verified`, and accepts `aud` against a configured **Client ID allowlist** (start with the portal Web client; add app clients later without changing link cardinality).

3. **Enablement (two layers):** Google sign-in is offered only when **both** are true: `auth.identity_provider` row `google` has `is_active`, **and** at least one Google Client ID is configured in deployment env/secrets. Catalog flags are not a substitute for Client IDs (ADR 0005 stores no OAuth client material). Portal may gate GIS on `VITE_GOOGLE_CLIENT_ID`; the API still enforces `is_active` and verification config.

4. **Provisioning:** Never create an Admin User from Google alone. Resolve in order: existing Identity link by `(google, sub)` → else match verified email (case-insensitive) to an Auth credential that is already admin-eligible (`is_admin`, verified, active) and **upsert** the Identity link. Password login remains available; linking Google does not clear `password_hash`. Unlink is out of scope for this slice.

5. **Errors:** Fail with a **generic** sign-in failure toward clients (no account-enumeration detail for missing email, non-admin, inactive, etc.).

6. **Apple:** Catalog entry remains for **End-user** app sign-in later. **Do not** expose Apple on the admin console. Admin Identity-provider sign-in is Google-only.

7. **Microsoft / Entra:** Still out of scope (unchanged from ADR 0003 intent).

8. **Future End users (non-binding sketch for the next ADR):** First Google/Apple success may create Auth credential + End user; same Google `sub` reuses one Identity link if the person later becomes an Admin on that credential. Detail and magic-link interaction belong in that future ADR.

## Considered options

| Topic | Rejected | Why |
| ----- | -------- | --- |
| Authorization-code exchange for admin SPA | Extra server round-trip | ID token verify matches portal needs; no Google API scopes required |
| One Identity link per OAuth Client ID | Pairwise / per-app rows | Conflicts with ADR 0005 uniqueness; Google `sub` is account-stable |
| Auto-create Admin from Google | Faster staff onboarding | Admin remains invite/provisioned; no public staff signup |
| Admin Apple parity with Google | Symmetric IdPs | Product: Apple is app/store-oriented; admin console is Google + password only |
| Feature flag separate from `is_active` + Client ID | Third switch | Two layers already cover product off and missing secrets |
| Hosted-domain (`hd`) allowlist now | Extra org assumption | Existing-admin email match is enough for v1 admin Google |

## Consequences

- Implement admin Google verify + login path; reuse existing admin JWT completion after credential resolution.
- Revise ADR 0003 decision text so admin auth is **password and/or Google**, not password-only.
- `rooted-portal-frontend` must relax password-only acceptance tests to allow Google while still forbidding Microsoft/MSAL/Entra.
- Ops: configure Google Web Client ID (allowlist) and keep `identity_provider.google.is_active` under operational control.
- Agents must not infer End-user Google/Apple HTTP from this ADR alone; must not add Admin Apple or Microsoft from NewLife by analogy.
