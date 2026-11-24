# Test passcodes: operation and beta smoke test

How to run the testing exception in [ADR 0016](../adr/0016-beta-fixed-otp-with-firebase-remote-config.md).

A test passcode **does not prove that the person owns the mailbox**. Anyone who knows the passcode can sign in as any allowlisted email. Allowlist only dedicated test accounts and domains that hold no private personal data.

## When a test passcode applies

All of these must hold. Otherwise the backend emails a random code.

1. `ENV` is set to exactly `dev` or `stg`. Never `prod`, any other value, or unset.
2. The Firebase credentials belong to project `rooted-app-dev`.
3. The policy was loaded less than 60 seconds ago and is valid.
4. `otp_test_mode_enabled` is `true`.
5. The email matches `otp_test_allowlist`.

Clients cannot ask for a mode. The OTP request response reports the selected one as `deliveryMode`: `email` or `fixed`.

## Settings

| Setting | Where | Default |
| --- | --- | --- |
| `otp_test_mode_enabled` | Firebase console, project `rooted-app-dev`, Remote Config, **Server** template, Boolean | `false` |
| `otp_test_allowlist` | Same template, JSON | `[]` |
| `OTP_FIXED_CODE` | Backend environment variable | built-in `123456` |

Use the **Server** template, not the Client template. The backend's service account needs permission to read it.

`OTP_FIXED_CODE` has a different failure behavior from the remote settings:

- Missing or malformed `OTP_FIXED_CODE` (anything but six ASCII digits): the built-in default passcode is used, and a warning is logged without any passcode.
- Missing, malformed, or expired remote policy: email mode.

### Allowlist

```json
[
  "tester@example.com",
  "*@test.example.com",
  "*@*.example.com"
]
```

| Rule | Covers | Does not cover |
| --- | --- | --- |
| `tester@example.com` | that email only | `tester+qa@example.com` |
| `*@test.example.com` | every email on that domain | `alice@a.test.example.com` |
| `*@*.example.com` | every email on any subdomain, at any depth | `alice@example.com` |

Case and surrounding whitespace are ignored. **One invalid rule disables the whole list.** Wildcards other than these three forms, regular expressions, non-ASCII characters, and rules covering a whole top-level domain (`*@*.com`) are invalid.

## Timing

- **Remote changes** are observed within about 60 seconds. Each instance refreshes separately.
- **Withdrawal** (disabled, removed from the list, policy unusable): once observed, outstanding fixed-code challenges that are no longer permitted are removed. The tester must request again. Re-enabling does not revive them.
- **Changing `OTP_FIXED_CODE`** takes effect when the backend restarts. Challenges issued with the old code are rejected.
- **Emailed codes** keep their original expiry through all of these changes.
- **Signed-in sessions** are not affected.

## Turning it on

1. Deploy this backend and the compatible Flutter app first.
2. Set `otp_test_allowlist`, check it, and publish.
3. Set `otp_test_mode_enabled` to `true` and publish.

To turn it off, set `otp_test_mode_enabled` to `false` and publish.

## Recovery

Look for these warnings in the backend log. They never contain codes, credentials, or allowlist entries.

| Log message | What to check |
| --- | --- |
| `Firebase credentials are not configured` | Credential file or `FIREBASE_CREDENTIALS_PATH` |
| `Firebase credentials belong to a project without test passcodes` | Credentials are not for `rooted-app-dev` |
| `Test passcode policy could not be loaded: <ErrorType>` | Network, service-account permission, or whether a Server template is published |
| `otp_test_mode_enabled is not a boolean` | Flag value |
| `otp_test_allowlist is not a JSON array of strings` / `contains an unsupported rule` | Allowlist value |
| `OTP_FIXED_CODE is not set` / `is not six ASCII digits` | Override; the default passcode is in use |

`Test passcode policy could not be applied: <ErrorType>` means Redis was unavailable while withdrawing challenges. The next successful refresh withdraws all fixed-code challenges, so testers may need to request again.

After the cause is fixed, a failed load is retried on demand after 10 seconds, and a loaded but invalid template after 60 seconds. No restart is needed, except for credential or environment changes.

If email mode returns `503`, check `RESEND_API_KEY` and Resend. Without a key, email mode fails in every environment, including local development.

## Beta smoke test

Run on the isolated beta deployment (`ENV=stg`). Automated tests use a fake Firebase and fake mail transport, so only this procedure verifies live permissions, refresh timing, mail delivery, and isolation. Record date, environment, version, and result for each step.

1. **Baseline:** flag `false`. Request a code for an allowlisted email. Expect `deliveryMode: email` and a delivered email.
2. **Enable:** publish the flag as `true`. Within 60 seconds an allowlisted request returns `fixed` and no email arrives. Sign in with the test passcode, with both a new and an existing test identity.
3. **Non-matching email:** request for an email outside the list. Expect `email`, a delivered email, and the test passcode rejected.
4. **One-time use:** verify the same challenge twice. Expect the second attempt to be rejected.
5. **Emailed code preserved:** with the flag `false`, request a code by email. Enable the flag, wait 60 seconds, and redeem the emailed code. Expect success.
6. **Withdrawal:** request a fixed challenge, then disable the flag. After 60 seconds, try to verify: rejected. Re-enable, wait 60 seconds, and try the same challenge again: rejected. Request again: works. Repeat by removing the email from the list instead.
7. **Invalid list:** add `"*"` to the list. Within 60 seconds requests return `email`. Restore the list and confirm recovery.
8. **Unavailable policy:** remove the service account's Remote Config permission. Within 60 seconds requests return `email` and the load warning is logged. Restore it and confirm recovery.
9. **Multiple instances:** with at least two instances, repeat steps 2 and 6 and send several requests. Expect every instance to agree after 60 seconds.
10. **Isolation:** confirm that beta and production use different databases and different Redis stores, and that production has `ENV=prod` and Firebase project `rooted-app-prod`. On production, request for an allowlisted email: expect `email`.
11. **Push:** send a test push on beta. Expect it to be delivered as before.

### Live verification record

Not performed yet. Record results on the ticket or here when the environments are available.
