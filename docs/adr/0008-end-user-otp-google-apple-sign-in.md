# ADR 0008 — End-user auth: email OTP + Google/Apple sign-in; optional onboarding registration

## Status

Accepted (2026-09-06). Supersedes the magic-link decision in **ADR 0003** for End users, and fulfills the "End-user Apple/Google HTTP flows still need a future ADR" placeholder ADR 0003 left open.

## Context

`rooted-app`'s onboarding wizard has no registration step today, and its Settings screen carries an ad hoc email+password register/login panel that has always contradicted ADR 0003's "no app password register/login as the product path" rule. `rooted-docs` PRD explicitly requires onboarding to have "no registration wall" so anonymous devotion use keeps working. ADR 0005 already reserved Identity-link schema for a future End-user Google/Apple sign-in. Push device registration (ADR 0007) already upserts `end_user_id` on every call, so binding a device to a newly-created account needs no new design — the client just calls the same endpoint again once signed in.

Product wants an account-creation moment inside onboarding without breaking the anonymous-first guarantee, and wants Google (and eventually Apple) as sign-in options for End users, not just Admins.

## Decision

1. **End-user first-party sign-in switches from magic link to email OTP** (one-time passcode): request sends a short numeric code, verify redeems it. Same ephemeral storage pattern as magic link (e.g. Redis TTL) — never persisted on Identity link rows.
2. **Google and Apple become End-user Identity-provider sign-in options** (HTTP flow), using the schema ADR 0005 already reserved. A first successful sign-in via either may create the Auth credential + End user, same rule already documented for Identity link.
3. **Apple ships code-complete but disabled** behind a client-side feature flag until the Apple Developer Program membership needed for the Sign-in-with-Apple entitlement is active. This is a client/rollout concern, not a backend one — the backend implements Apple as a normal Identity provider with no special-casing.
4. **The existing password-based Settings register/login panel is retired** in favor of the same OTP/Google/Apple set used in onboarding — one End-user auth surface, not two.
5. **Onboarding gains an optional, skippable "Register" step**, placed last (after the reminder step, before entering Today). Skippable to preserve the "no registration wall" / anonymous-use PRD guarantee, and because Apple's App Store review disfavors gating core functionality behind forced account creation.
## Consequences

- "Magic link" terminology retires in favor of "OTP" wherever End-user auth is described.
- Agents must not reintroduce password register/login as an End-user path — it was already forbidden by ADR 0003 and is now also gone from the client.
- Google Identity provider is used by both Admin (ADR 0006) and End user; Apple Identity provider stays End-user-only, never the admin console.
- Push device→account binding needs no new endpoint or flow: re-calling the existing `PUT /api/v1/push/devices/{device_key}` after sign-up/sign-in rebinds `end_user_id` for free (ADR 0007).
- `rooted-docs` PRD/sitemap need updating to drop the "no registration wall" wording in favor of "skippable registration step" (tracked separately, not part of this ADR).
