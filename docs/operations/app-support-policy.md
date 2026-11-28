# App support policy: configure, activate, roll out

How to run the minimum supported App build ([ADR 0017](../adr/0017-staging-release-tags-and-app-support-policy.md), ROO-163, ROO-171). The HTTP contract is in [docs/api/app-support-policy.md](../api/app-support-policy.md).

This code ships in **compatible** mode. Deploying it rejects nothing. Enforcement starts only when an operator sets `APP_SUPPORT_ENFORCEMENT=enforced`.

## Where the policy lives

| What | Where | Change takes effect |
| --- | --- | --- |
| The policy (minimum builds, update links) | **System settings** in each environment's own database: namespace `app_support`, keys `ios` and `android` | Next request after the save. No restart |
| Enforcement on/off | `APP_SUPPORT_ENFORCEMENT` environment variable on the Render service | After a restart |

Staging and production have separate databases, so each environment has its own `app_support.ios` and `app_support.android`. Clients cannot pick the environment. The environment name in responses comes from the server's `ENV`.

The old `APP_SUPPORT_POLICY` environment variable is gone. It is not read anymore. Delete it from Render.

### Policy format

Each platform is one system setting with `value_type` `object`:

```json
{"minimum_build": 42, "latest_build": 45, "update_url": "https://testflight.apple.com/join/AbCdEf"}
```

```json
{"minimum_build": 17, "update_instructions": "Download the newest staging APK from the team drive and install it over this one."}
```

- `minimum_build` (required): a JSON integer from 0 to 999999999. Builds below it must update. Use `0` to support every build.
- `latest_build` (optional): an integer, not below `minimum_build`. Informational only: it never forces an update.
- `update_url` (optional): an absolute `https://` URL. Use it for TestFlight, the stores, or a download page.
- `update_instructions` (optional): plain text for direct installs with no link. It is not translated.
- Give at least one of `update_url` and `update_instructions`.
- Unknown fields are errors. Numbers must be JSON numbers: `"42"` (a string) is invalid.

### Saves are checked

The admin setting API checks every create and update in the `app_support` namespace. A bad value is refused and the saved policy stays in force:

- `400 SYSTEM_SETTING_VALUE_INVALID`, with `context.reasons` listing each problem.
- Also refused: a key other than `ios` / `android` (lowercase), or a `value_type` other than `object`.

Other namespaces keep the generic system-setting rules.

### Missing or invalid policy

Each platform is read on its own. A broken iOS setting leaves Android working.

| Problem | Result for that platform |
| --- | --- |
| No setting, soft-deleted, or `is_active` false | Unavailable |
| Stored value fails the field rules (saved by SQL, restored from the recycle bin, or saved before this check existed) | Unavailable |

"Unavailable" means:

- Lookup: `503 APP_SUPPORT_POLICY_UNAVAILABLE`. Policy-aware Apps show connection/retry. Never update-required.
- Gate in `compatible`: no effect.
- Gate in `enforced`: every request from that platform gets `503 APP_SUPPORT_POLICY_UNAVAILABLE`. **Never enforce with a missing or invalid policy.**

The admin API cannot switch `is_active` back on. To fix an inactive setting, delete it permanently (`DELETE …/system/settings/<id>` with body `{"permanent": true}`) and create it again. A restore from the recycle bin is not checked, so look up the restored value afterwards.

The backend logs a line starting `System setting app_support.<platform>` when a platform becomes unavailable. Policy values contain no secrets.

## Change the policy

Needs an Admin User with the `system:setting` permission: `system:setting:read` to look, `system:setting:update` to change, `system:setting:create` for the first save, `system:setting:delete` to remove. Use the generic system-setting screen in the admin portal, or the admin API below. `$ADMIN` is `https://api-stg.rootedfaith.app/admin/api/v1` (or production) and `$TOKEN` is an Admin access token.

1. **Record the current value first.** There is no setting history. This is your rollback:

   ```bash
   curl -s "$ADMIN/system/settings/by-key?namespace=app_support&setting_key=ios" -H "Authorization: Bearer $TOKEN" | tee ios-before.json
   ```

   Note the `id` and `value`.

2. **Save the new value:**

   ```bash
   curl -s -X PUT "$ADMIN/system/settings/<id>" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     -d '{"value": {"minimum_build": 42, "update_url": "https://testflight.apple.com/join/AbCdEf"}, "remark": "ROO-xxx raise iOS minimum"}'
   ```

   `200` means saved. `400 SYSTEM_SETTING_VALUE_INVALID` means nothing changed; fix the value.

3. **First time in an environment** (the setting does not exist yet), create it instead:

   ```bash
   curl -s -X POST "$ADMIN/system/settings" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     -d '{"namespace": "app_support", "setting_key": "ios", "value_type": "object", "value": {"minimum_build": 0, "update_instructions": "Install the newest build."}}'
   ```

   Do the same for `android`. Policy values are not part of the code release, so there is no seed command for them.

4. Check the effective policy (below). Only then announce the change.

### When it takes effect

- The save deletes the cached copy in Redis. **The next lookup or gated request after the save returns reads the new value**, on every instance (they share Redis). Lookup and gate change together.
- Rare edge: if an App request misses the cache in the few milliseconds between the save and its database commit, it can cache the old value again. That copy expires after **60 seconds** at most.
- A change made by SQL, not through the admin API, does not clear the cache. It takes effect within **60 seconds**.
- During a Redis and database outage, an instance can keep using its last read for up to **5 minutes** (see below).

## Check the effective policy

```bash
curl -s 'https://api-stg.rootedfaith.app/api/v1/app-support/policy?platform=ios'
curl -s 'https://api-stg.rootedfaith.app/api/v1/app-support/policy?platform=android'
```

The response shows the values in force and the `enforcement` mode. Lookup and the gate read the same source, so this is also what the gate uses. A `503` means that platform is unavailable: check the setting and the `System setting app_support` log lines.

## Per-request cost

Only gated App requests in `enforced` mode and policy lookups read the policy. In `compatible` mode gated requests read nothing.

| Case | Work |
| --- | --- |
| Cache hit (normal) | One Redis `GET` |
| Cache miss (first read, after a save, or after the 60 s cache expiry) | Redis `GET`, one database `SELECT` on its own short session, one Redis `SET` |
| Setting missing | Redis `GET` and a database `SELECT` on **every** request. Missing values are not cached |
| Redis down | A database `SELECT` on every request |

Measured locally (Redis and Postgres in Docker on macOS, 2026-11-28): Redis `GET` median 0.3 ms (p95 0.9 ms); cache miss median 52 ms (p95 136 ms), almost all of it Docker networking for the database round trips. On a hit, the gate opens no database session.

The policy read uses its own database session because the gate runs before the App API's request session and auth.

## Redis or database outage

The gate never admits a build it cannot check. It also does not wait on a hung backend: a Redis read times out after 0.5 s and a database read after 2 s.

| Redis | Database | Result |
| --- | --- | --- |
| Up | Up | Normal |
| Down or slow | Up | Read the database on every request. Same answers, more database load |
| Any | Down or slow, on a read that needs it | Use this instance's last successful read if it is at most **5 minutes** old. Otherwise that platform is unavailable (`503`) |

What that means in `enforced` mode:

- An outage never turns into update-required, and never lets an unsupported build through. The worst case is an answer up to 5 minutes old.
- After 5 minutes with both down, every App request from that platform gets `503 APP_SUPPORT_POLICY_UNAVAILABLE`. When the database is down, App features fail anyway, so this adds no new outage.
- The last-known-good copy is per instance and in memory. A freshly started instance has none, so it fails closed until it can read.

While Redis is down, an admin save fails (`500`) and changes nothing, because the save cannot clear the cached copy. Save again once Redis is back.

Emergency: set `APP_SUPPORT_ENFORCEMENT=compatible` and restart to stop all policy checks.

## Turn enforcement on or off

- On: set `APP_SUPPORT_ENFORCEMENT=enforced`, then save and deploy.
- Off (emergency): set it to `compatible`, or delete it, then save and deploy. Requests pass again after the restart.

Empty means `compatible`. Any other value makes the service fail to start.

Before turning it on:

1. Both platforms return `200` from the policy lookup in that environment.
2. Policy-aware builds (they send `X-App-Platform` / `X-App-Build`) are installed by everyone who still needs access. In enforced mode, legacy builds without the headers get `400 APP_IDENTITY_INVALID`. They have no update screen, so tell those testers to update by hand first.
3. No browser client still uses this API. A browser cannot send a mobile identity (`ios`/`android`), so in enforced mode every browser request (for example a web/PWA build of the App registered in `MEMBER_WEB_APPS`) gets `400 APP_IDENTITY_INVALID`.
4. Check that `enforcement` reads `enforced` after the deploy.

## Rollout order

Never skip a step.

1. **Compatible backend.** Deploy this code with no `APP_SUPPORT_ENFORCEMENT` (that is, `compatible`). Create `app_support.ios` and `app_support.android` with `minimum_build` at or below every build in use (e.g. `0`). Check the lookup.
2. **Policy-aware App.** Publish Flutter builds that send identity and check the policy (ROO-165). Make them installable on each platform. Ask testers on older builds to update by hand: those builds cannot show an update screen.
3. **Enforce identity.** Once the old builds are gone, set `APP_SUPPORT_ENFORCEMENT=enforced`. `minimum_build` stays low, so only requests with no identity or invalid identity are rejected.
4. **Raise the minimum (breaking change only).**
   1. Make the replacement build installable first: on TestFlight or the store, or downloadable with written instructions.
   2. Save the higher `minimum_build` for that platform only. Check the lookup.
   3. Deploy the incompatible backend **after** the higher minimum is in force. Never deploy a backend that breaks supported builds while the old minimum still admits them.

   Apps already open get `426` on their next request and switch to the update screen.

Compatible backend changes never need a higher minimum.

## Rollback

Plan the image, policy, and database together. A **lower minimum must never admit an App the running backend cannot serve.**

- **Undo a policy change:** `PUT` the value you recorded in step 1 of [Change the policy](#change-the-policy). It applies on the next request. There is no setting history, so without that record you must rebuild the old value by hand.
- **Back to an older image:** first check that the database is in a state that image works with (migrations are done by hand). The policy is in the database, so it stays the same across image changes. Then look at the policy. If the older image cannot serve the newest builds, you cannot fix that with the minimum, because a minimum only blocks old builds. Roll forward instead, or accept that.
- **Lower a minimum** only when the running backend still serves the builds that become allowed again.
- **Turn enforcement off** (`compatible`) as an emergency step when a bad policy blocks users. It admits every build again, including incompatible ones.
- Record App build, API URL, backend image tag, policy values, and enforcement mode together for each acceptance run ([staging releases](staging-releases.md)).

## Not covered here

- No dedicated admin screen. Use the generic system-setting screen or API.
- Builds released before ROO-165 cannot show the update screen. That cannot be added to them later.
- `X-App-*` headers are not authentication. A client can lie about its build. The gate limits compatibility, not access.
