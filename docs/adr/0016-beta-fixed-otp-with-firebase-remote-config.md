# ADR 0016 — Beta fixed-code sign-in with Firebase Remote Config

## Status

Accepted (2026-10-10; discovery began 2026-10-09). The specification is published; implementation and deployment are not yet delivered.

Specification: [GitHub #117](https://github.com/rooted-faith/rooted-core-api/issues/117), synchronized as [Linear ROO-55](https://linear.app/jayhsia/issue/ROO-55/spec-configure-beta-test-passcodes-with-firebase-remote-config) in Project `rooted core api`, state `Backlog`, labels `spec` and `ready-for-agent` at publication.

## Context and confirmed choices

Beta testing needs a way to switch between delivering an email OTP and using a fixed verification code for faster End-user sign-in. Firebase Remote Config was selected over Rooted System Settings as the remote control surface, with the backend evaluating the OTP mode. The fixed code remains configured in backend environment variables.

Beta and production use separate data environments. The fixed-code path is a testing exception to ADR 0008's email-delivered OTP flow: it does not prove ownership of the supplied mailbox.

Beta may expand from invited testing to public testing without introducing another release environment. Fixed-code sign-in is restricted to explicitly allowlisted, dedicated internal test email identities, including first-use creation of a test account. Other beta emails always receive a random code by email, even when the remote test-mode flag is enabled. The allowlist limits which identities are accessible with the shared code; it does not authenticate the person entering that code, so allowlisted accounts must not hold private personal data.

The App retains its email-entry, request, and manual code-entry flow. A fixed code replaces random code generation without delivering an email; challenges retain expiry, one-time consumption, and request rate limits. Re-requesting can make the same fixed code valid again, so the code value itself is not unique per challenge.

The backend supplies the default fixed test passcode `123456`. `OTP_FIXED_CODE` can override it with a six-digit numeric string, including leading zeros. Missing or malformed overrides use the default and record a configuration diagnostic without logging any passcode; they must not cause an otherwise eligible fixed-code request to switch to random-code email delivery.

The backend refreshes the remote configuration every 60 seconds. Missing or malformed configuration, or expired configuration that cannot be refreshed, falls back to random-code email delivery. This does not imply mail delivery will succeed; existing delivery-failure handling remains applicable.

The mode flag and test email allowlist are managed in Firebase Remote Config's server template, evaluated by the backend rather than supplied by the App. `otp_test_mode_enabled` defaults to `false`.

The allowlist supports exact email addresses, exact domains, and subdomain rules in a plain JSON string array. A domain rule extends shared-passcode access to every beta identity matching that domain, including newly provisioned identities; dedicated test domains should be used.

Only the exact backend environment values `dev` and `stg` are eligible for fixed-code sign-in. Beta uses the existing `stg` environment name. Both `dev` and `stg` use Firebase project `rooted-app-dev`; production uses `ENV=prod` and `rooted-app-prod`. Production and unrecognized environment values must reject fixed-code mode regardless of the remote flag. The existing broad `IS_DEV` predicate must not be used as the eligibility gate.

The OTP request response reports the mode actually selected by the backend. Flutter uses this to show a test-passcode instruction for fixed-code challenges and the usual email instruction for emailed challenges. The App never receives the fixed code itself. Copy shown before requesting a challenge must accommodate both outcomes without claiming an email has already been sent.

Once the backend observes test-mode disablement or removal of an email from the allowlist, it must reject that identity's outstanding fixed-code challenge. Expired configuration that cannot be refreshed also revokes eligibility for fixed-code verification. Previously emailed random-code challenges keep their original expiry when test mode is enabled. Changing the backend fixed code invalidates outstanding challenges issued with the old fixed code; testers must request a new challenge.

The dev-only fallback that logs a random OTP and reports success when Resend credentials are absent is retired. Email-mode requests must actually deliver through the mail provider; missing mail credentials or delivery failure invalidate the newly issued challenge and return the existing retryable `503` response. Fixed-code requests do not require mail credentials.

## Configuration and matching contract

| Setting | Source | Default |
| --- | --- | --- |
| `otp_test_mode_enabled` | Firebase Remote Config server template, boolean | `false` |
| `otp_test_allowlist` | Firebase Remote Config server template, JSON string array | `[]` |
| `OTP_FIXED_CODE` | Backend environment override | `123456` |

Example value of `otp_test_allowlist`:

```json
[
  "tester@example.com",
  "*@test.example.com",
  "*@*.example.com"
]
```

Only these three rule forms are supported. Rules are not arbitrary regular expressions or general-purpose glob expressions: `**`, backslash escapes, `?`, bracket expressions, bare `*`, and `*@*` are unsupported. Matching strips surrounding whitespace and lowercases emails and rules; it preserves dots and `+tag` in the email's local part. Duplicate rules do not change the result.

An exact email rule matches only that complete email. An exact-domain rule matches all valid emails whose domain equals the configured domain, excluding subdomains. A subdomain rule matches one or more subdomain levels, excluding the base domain itself. Domain comparisons operate on the parsed email domain and complete label boundaries, not substring search or unrestricted glob matching against the entire email.

| Rule | Matches | Does not match |
| --- | --- | --- |
| `tester@example.com` | `tester@example.com` | `tester+qa@example.com`, `other@example.com` |
| `*@test.example.com` | `alice@test.example.com` | `alice@a.test.example.com` |
| `*@*.example.com` | `alice@a.example.com`, `alice@a.b.example.com` | `alice@example.com`, `alice@evil-example.com`, `alice@example.com.attacker.com` |

The complete array is validated before use. An empty array or any invalid rule disables fixed-code eligibility and restores email delivery; valid entries are not partially applied from an invalid array. With a valid array, matching any rule is sufficient, but environment, project, flag, and configuration freshness requirements still apply.

## API and App boundary

`POST /api/v1/auth/otp` retains its `{email}` request and adds the camelCase response field `deliveryMode`, with values `email` or `fixed`, alongside the existing acknowledgement `message`. Mode selection depends on the test policy, not whether the email already has an account. Fixed-mode acknowledgement and App instructions must not claim that email was sent. No code or allowlist is returned to the App.

`POST /api/v1/auth/otp/verify` retains its `{email, code}` request and existing login response. The App cannot request or override the server-selected mode. Challenge origin must distinguish emailed and fixed-code challenges; matching the numeric code alone must not cause an emailed challenge to be treated as a test challenge.

Flutter consumes the request response through its repository and auth state, updates instructions after each request or resend, and keeps the current manual code-entry and resend countdown. Pre-request copy is neutral; fixed-mode copy directs testers to the passcode provided by the test team. All existing supported App locales must remain consistent.

## Scope and verification

Implementation spans Core API policy/configuration, OTP challenge handling, mail delivery and response serialization, plus Flutter auth response handling and copy. No new sign-in endpoint, database migration, Portal feature, Google/Apple behavior, or Admin sign-in path is required. Configuration deployment and credentials must be verified separately from repository configuration; this ADR does not claim that live Firebase or Render settings have been changed.

Required implementation verification covers production and unknown-environment blocking; environment/project isolation; exact-email, domain, and subdomain boundaries; invalid and stale remote configuration; missing or malformed fixed-code overrides; request-before-verify, expiry, quota and atomic consumption; withdrawal of fixed-code eligibility; preservation of emailed challenges; delivery failure and removal of the dev logging fallback; and Flutter mode-specific instructions after initial requests and resends. Passing application tests alone does not establish that live project permissions, refresh timing, or deployment isolation are correct.

Implementation, deployment, and tracker changes are outside this discovery step.
