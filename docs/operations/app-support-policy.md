# App support policy: configure, activate, roll out

How to run the minimum supported App build ([ADR 0017](../adr/0017-staging-release-tags-and-app-support-policy.md), ROO-163). The HTTP contract is in [docs/api/app-support-policy.md](../api/app-support-policy.md).

This code ships in **compatible** mode. Deploying it rejects nothing. Enforcement starts only when an operator sets `APP_SUPPORT_ENFORCEMENT=enforced`.

## Settings

Both are environment variables on the backend service. Each Render service (staging, production) has its own.

| Variable | Default | Meaning |
| --- | --- | --- |
| `APP_SUPPORT_POLICY` | unset | JSON policy, keyed by environment, then platform |
| `APP_SUPPORT_ENFORCEMENT` | `compatible` | `compatible` never rejects. `enforced` turns on the request gate. Empty means `compatible`. Any other value makes the service fail to start |

### Policy format

```json
{
  "stg": {
    "ios": {"minimum_build": 42, "latest_build": 45, "update_url": "https://testflight.apple.com/join/AbCdEf"},
    "android": {"minimum_build": 17, "update_instructions": "Download the newest staging APK from the team drive and install it over this one."}
  },
  "prod": {
    "ios": {"minimum_build": 30, "update_url": "https://apps.apple.com/app/id0000000000"},
    "android": {"minimum_build": 12, "update_url": "https://play.google.com/store/apps/details?id=app.rootedfaith"}
  }
}
```

- The service only reads the key that matches its own `ENV` (`dev`, `stg`, `prod`). A staging service ignores a `prod` block. Clients cannot pick the environment.
- `minimum_build` (required): a JSON integer from 0 to 999999999. Builds below it must update. Use `0` to support every build.
- `latest_build` (optional): an integer, not below `minimum_build`. Informational only: it never forces an update.
- `update_url` (optional): an absolute `https://` URL. Use it for TestFlight, the stores, or a download page.
- `update_instructions` (optional): plain text for direct installs with no link. It is not translated.
- Give at least one of `update_url` and `update_instructions`.
- Unknown fields are errors. Numbers must be JSON numbers: `"42"` (a string) is invalid.

### Missing or invalid policy

Each platform is checked on its own. A broken iOS entry leaves Android working.

| Problem | Result |
| --- | --- |
| Variable unset or empty, not JSON, not an object, or no object for this `ENV` | Both platforms unavailable |
| A platform is missing or fails validation | That platform unavailable |
| Extra platform key (e.g. `web`) | Ignored, error logged |

"Unavailable" means:

- Lookup: `503 APP_SUPPORT_POLICY_UNAVAILABLE`. Policy-aware Apps show connection/retry.
- Gate in `compatible`: no effect.
- Gate in `enforced`: every request from that platform gets `503 APP_SUPPORT_POLICY_UNAVAILABLE`. **Never enforce with a missing or invalid policy.**

Every problem is logged once at startup, beginning with `APP_SUPPORT_POLICY`. Policy values contain no secrets.

## Update the policy

1. Write the new JSON. Validate it locally:

   ```bash
   ENV=stg APP_SUPPORT_POLICY="$(cat policy.json)" uv run python -c '
   from portal.config import settings
   from portal.domain.app_support.constants import AppPlatform
   from portal.infrastructure.app_support.env_policy_source import EnvAppSupportPolicySource
   source = EnvAppSupportPolicySource(raw=settings.APP_SUPPORT_POLICY, environment=settings.ENV)
   for platform in AppPlatform:
       print(platform.value, source.get(platform))'
   ```

   Both platforms must print a policy, not `None`.

2. In Render, open the service → Environment → set `APP_SUPPORT_POLICY` → save and deploy. The selected image stays the same.
3. **When it takes effect:** the policy is read once per process. The old value stays in force until the restarted instance is live, and the new value then applies to lookup and the gate together. There is no live reload and no cache to clear. While Render swaps instances, old and new instances can answer side by side for a short time. Wait for the deploy to finish before you rely on the new value.
4. Check the effective policy (step below). Only then announce the change.

## Check the effective policy

```bash
curl -s 'https://api-stg.rootedfaith.app/api/v1/app-support/policy?platform=ios'
curl -s 'https://api-stg.rootedfaith.app/api/v1/app-support/policy?platform=android'
```

The response shows the values in force and the `enforcement` mode. Lookup and the gate read the same source, so this is also what the gate uses. A `503` means that platform is unavailable. Check the startup logs for the `APP_SUPPORT_POLICY` line.

## Turn enforcement on or off

- On: set `APP_SUPPORT_ENFORCEMENT=enforced`, then save and deploy.
- Off (emergency): set it to `compatible`, or delete it, then save and deploy. Requests pass again after the restart.

Before turning it on:

1. Both platforms return `200` from the policy lookup in that environment.
2. Policy-aware builds (they send `X-App-Platform` / `X-App-Build`) are installed by everyone who still needs access. In enforced mode, legacy builds without the headers get `400 APP_IDENTITY_INVALID`. They have no update screen, so tell those testers to update by hand first.
3. No browser client still uses this API. A browser cannot send a mobile identity (`ios`/`android`), so in enforced mode every browser request (for example a web/PWA build of the App registered in `MEMBER_WEB_APPS`) gets `400 APP_IDENTITY_INVALID`.
4. Check that `enforcement` reads `enforced` after the deploy.

## Rollout order

Never skip a step.

1. **Compatible backend.** Deploy this code with no `APP_SUPPORT_ENFORCEMENT` (that is, `compatible`). Set `APP_SUPPORT_POLICY` with `minimum_build` at or below every build in use (e.g. `0`). Check the lookup.
2. **Policy-aware App.** Publish Flutter builds that send identity and check the policy (ROO-165). Make them installable on each platform. Ask testers on older builds to update by hand: those builds cannot show an update screen.
3. **Enforce identity.** Once the old builds are gone, set `APP_SUPPORT_ENFORCEMENT=enforced`. `minimum_build` stays low, so only requests with no identity or invalid identity are rejected.
4. **Raise the minimum (breaking change only).**
   1. Make the replacement build installable first: on TestFlight or the store, or downloadable with written instructions.
   2. Set `minimum_build` to that build's number for that platform only.
   3. Deploy the incompatible backend **after** the higher minimum is in force. Never deploy a backend that breaks supported builds while the old minimum still admits them.

   Apps already open get `426` on their next request and switch to the update screen.

Compatible backend changes never need a higher minimum.

## Rollback

Plan the image, policy, and database together. A **lower minimum must never admit an App the running backend cannot serve.**

- **Back to an older image:** first check that the database is in a state that image works with (migrations are done by hand). The policy carries over across image changes. Then look at the policy. If the older image cannot serve the newest builds, you cannot fix that with the minimum, because a minimum only blocks old builds. Roll forward instead, or accept that.
- **Lower a minimum** only when the running backend still serves the builds that become allowed again.
- **Turn enforcement off** (`compatible`) as an emergency step when a bad policy blocks users. It admits every build again, including incompatible ones.
- Record App build, API URL, backend image tag, policy values, and enforcement mode together for each acceptance run ([staging releases](staging-releases.md)).

## Not covered here

- No admin UI, database table, or live reload. A policy change is a service restart.
- Builds released before ROO-165 cannot show the update screen. That cannot be added to them later.
- `X-App-*` headers are not authentication. A client can lie about its build. The gate limits compatibility, not access.
