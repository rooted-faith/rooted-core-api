# Staging release tags and minimum supported App builds

Status: Accepted (2026-11-28). This document records the agreed design; it does not indicate implementation, deployment, or live verification.

Detailed specification: [Tag-selected staging releases and minimum supported App builds](../specs/staging-releases-and-app-version-policy.md). Published tracker: [ROO-161](https://linear.app/jayhsia/issue/ROO-161/spec-tag-selected-staging-releases-and-minimum-supported-app-builds) / [GitHub #162](https://github.com/rooted-faith/rooted-core-api/issues/162).

Continuous deployment from `main` can replace the backend while an installed App is still being tested against an earlier contract. Select staging releases explicitly with tags, give Flutter a staging entry point with a default deployed API URL, and require updates only for App builds below a configured support minimum.

## Agreed decisions

### Staging release selection

- Merges to `main` run checks without building a container image or deploying staging.
- Pushing a tag matching `stg.YYMMDD.N` builds an image with that same tag and automatically deploys it to staging. `N` starts at 1 each day and increases for subsequent releases that day; for example, `stg.261128.1`.
- The tagged commit must be reachable from `main`; it need not be the latest commit. Reject tags pointing to unmerged work.
- Published release tags and images are not overwritten or reused. Later merges to `main` do not change the selected staging image.
- Rollback is a human operation in Render: select a retained image and deploy it. Do not create another tag, rebuild the image, or add an Actions approval or rollback workflow.
- A container rollback requires compatible database state. Human-managed migrations and data changes need their own recovery plan.

### Flutter staging configuration

- Add `main_staging.dart` and a `staging` flavor with `https://api-stg.rootedfaith.app` as its default API base URL.
- A release-mode staging run must not require a repeated `--dart-define=API_BASE_URL=...` argument. Preserve the override for intentional testing.
- Build mode (`debug` / `release`) and backend environment are separate choices. A staging release build connects to the staging API.
- An API URL selects an environment, not a backend commit. Record the App build, API URL, and backend image tag together for acceptance.
- Supporting installed older App builds does not require side-by-side installation or another bundle identifier. The native identifier and signing arrangement for the new flavor still need verification against the existing Flutter project.

### Minimum supported App builds

- Compare the installed App build number with a minimum supported build for its platform and environment. Do not force an update merely because the App differs from the latest build.
- Below the minimum: block normal use and require an update. At or above the minimum: allow use; a newer available build may be advertised without blocking.
- Check policy on App startup and return to the foreground. Routine App API requests must also carry platform/build identity so the backend can reject unsupported builds with a stable error understood by the App.
- Keep the unauthenticated policy lookup and the unsupported-build error stable and accessible without passing the normal App version gate. Exact API paths, headers, and error shape will be specified before implementation.
- Publish an installable replacement App before raising the minimum. Directly installed staging builds need an update instruction; distribution through TestFlight or a store can supply an appropriate update destination.
- Compatible API changes do not require raising the minimum. For breaking changes, coordinate the replacement App, policy change, and backend deployment; request-level enforcement must cover Apps already running.
- An older App without version checking or build identity cannot be made to display the update screen remotely. Introduce that capability before depending on it for a breaking rollout, and specify handling of missing or invalid client identity before enforcement.
- Backend rollback and minimum-version policy rollback must be considered together: a lowered support minimum must never admit an App incompatible with the selected backend.

### Policy lookup failure

- If a valid support policy cannot be fetched, show a connection/retry state and block entry into normal App use until the policy can be checked successfully.
- Only a successfully checked policy confirming that the installed build is below the minimum can trigger forced-update messaging. Network failures, timeouts, and invalid policy responses must not be presented as an outdated App.
- Apply this behavior on startup and foreground rechecks; a previously cached policy does not authorize bypassing a failed recheck.

## Implementation requirements

- Validate tag syntax and main ancestry before publishing or deploying.
- Serialize staging deployments and wait for an in-progress Render rollout to settle before starting another. Build failure must prevent deployment.
- Verify deployed readiness and report the selected image; sending a deploy request alone is not acceptance evidence.
- Define monotonic build numbering per platform/environment, policy ownership and storage, missing/invalid identity handling, and the stable HTTP contract during implementation planning.
- API implementation belongs to `rooted-core-api`; Flutter flavor, native configuration, and update UI belong to `rooted_flutter`. Keep implementation tickets repository-scoped and link their dependencies if tickets are requested.

## Trade-offs

Tag-driven staging adds an explicit release selection step while avoiding automatic replacement during acceptance. Render rollback reuses existing operational controls. Minimum-build enforcement bounds the supported client set, but does not remove the need for compatible policy/error contracts or coordinated App distribution and database changes.
