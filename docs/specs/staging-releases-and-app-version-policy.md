# [Spec] Tag-selected staging releases and minimum supported App builds

## Problem Statement

An installed Rooted App selects an API URL, not an API commit. Today, merging backend work into main builds and deploys a new image to the same staging service. A developer testing an App against one backend can therefore encounter a different contract without intentionally changing the acceptance environment.

Running Flutter in release mode also requires the developer to repeat the staging API URL override because there is no staging entry point and flavor. Finally, a deliberate breaking backend release needs a predictable way to stop unsupported installed Apps and explain how to update, including Apps already open when the backend changes.

## Solution

Keep main as a checked integration branch. Select staging releases explicitly by pushing a new tag such as `stg.261128.1`. Only a valid staging tag on a commit already merged into main builds the corresponding tagged image and deploys staging. Subsequent main merges leave that environment unchanged. Operators roll back by selecting a retained image directly in Render.

Provide a Flutter staging entry point and flavor whose default backend is `https://api-stg.rootedfaith.app`. Release mode remains a build choice independent of environment, and developers no longer repeat the API URL for ordinary staging runs.

Introduce platform- and environment-specific minimum supported App build policies. Check on startup and return to the foreground, and enforce support on normal App API requests. Only a confirmed build below the minimum requires an update; merely being older than the latest build does not. A failed policy lookup shows a connection/retry screen and prevents normal use until a successful check.

## User Stories

1. As a developer, I want main merges to run checks without deploying staging, so that integration work cannot interrupt an ongoing acceptance session.
2. As a developer, I want main merges to avoid building unused container images, so that image builds happen when I select a staging release.
3. As a release operator, I want to publish a short date-based staging tag, so that I can identify the selected release without a long name.
4. As a release operator, I want a valid staging tag to build and deploy automatically, so that selecting the tag is the deployment decision without another approval step.
5. As a release operator, I want tags on unmerged commits rejected, so that staging only receives integrated work.
6. As a release operator, I want to select an older commit reachable from main, so that staging does not have to use the latest main commit.
7. As a tester, I want staging to remain on its selected image after later main merges, so that an App/API acceptance combination stays stable.
8. As a release operator, I want published tags and images preserved, so that an existing release name continues to identify the same artifact.
9. As a release operator, I want invalid tags and failed image builds to leave the running service unchanged, so that a failed release cannot replace staging.
10. As a release operator, I want deployments serialized through completion, so that simultaneous releases cannot race while changing the service image.
11. As a release operator, I want a failed Render request or readiness check reported as a failure, so that a successful workflow means the selected release is actually running.
12. As a release operator, I want to roll back directly in Render using an existing image, so that recovery requires neither a new tag nor another image build or Actions run.
13. As a release operator, I want production release operations to leave staging release metadata unchanged, so that its displayed version describes its selected image.
14. As a Flutter developer, I want a staging entry point and flavor with the staging URL as the default, so that I do not type an API URL override every time.
15. As a Flutter developer, I want release-mode staging builds, so that I can test deployed backend behavior with release-mode App performance.
16. As a Flutter developer, I want to retain an intentional API URL override, so that exceptional testing does not require editing source defaults.
17. As a developer, I want staging native configuration to reuse the intended development installation identity, so that I am not forced to provision another bundle identifier merely to test staging.
18. As a release operator, I want each acceptance record to identify the App build, API URL, and backend image, so that results can be reproduced.
19. As an End user, I want a supported build to open normally even when a newer build exists, so that compatible updates are not unnecessarily mandatory.
20. As an End user, I want an unsupported build to show a clear update screen, so that I understand why normal use is blocked and how to obtain the replacement.
21. As an anonymous reader, I want the support check to work before sign-in, so that the App can explain an update requirement without authentication.
22. As an End user, I want my App checked again when I return to it, so that a support-policy change is recognized without restarting the process.
23. As an End user, I want unsupported-build responses during an active session to open the same update screen, so that keeping the App open cannot produce confusing feature errors.
24. As an End user, I want network failures to show a retry action rather than an outdated-App warning, so that I receive accurate recovery guidance.
25. As an End user, I want a successful retry to evaluate support and continue appropriately, so that a transient outage does not permanently block my App.
26. As an End user, I want update and connection screens to preserve my sign-in and private writing, so that a policy change does not discard my data.
27. As a release operator, I want separate policies for iOS and Android in each backend environment, so that one platform's release timing does not block the other platform or production.
28. As a release operator, I want to make a replacement App installable before raising the minimum, so that blocked users have an available update path.
29. As a staging tester installing builds directly, I want practical installation instructions even without a store link, so that I can update using the current distribution method.
30. As a release operator, I want to introduce policy-aware clients before enforcing their identity, so that existing beta builds are not unexpectedly locked out during rollout.
31. As a release operator, I want a documented backend, policy, and database rollback sequence, so that rollback does not admit an App incompatible with the selected image.
32. As an administrator or integration consumer, I want the mobile support gate scoped to App traffic, so that admin access, health checks, and webhooks continue to operate.

## Implementation Decisions

### Release selection and deployment

- Replace automatic main-to-staging deployment with checks on main and a staging-tag-triggered build/deploy pipeline. Preserve the existing production release trigger and deployment mechanism except for removing its mutation of staging-only version metadata.
- Use `stg.YYMMDD.N`, with a valid calendar date and a positive daily sequence starting at 1, for example `stg.261128.1`. Operators select the next unused sequence; do not add automatic tag creation. Production's existing version tags remain distinct.
- Validate the tag and resolve its commit before any image publication or Render mutation. Accept commits reachable from main, including historical commits. Fetch enough Git history for this check to be reliable.
- Build the selected commit and publish an image with exactly the staging tag. Preserve its identity and record its digest. Never move a published tag or overwrite an existing release image; a deployment retry reuses the published artifact rather than rebuilding it under the same name.
- The tag push is the deployment authorization. Do not add a manual Actions approval, staging freeze switch, release branch, or second staging service.
- Serialize staging image selection and rollout, including completion of an asynchronous Render deployment. A concurrency lock released immediately after sending the deploy request is insufficient. Do not interrupt an in-progress deployment to start another.
- Build, publish, API-request, and readiness failures must be visible and prevent a success result. Verify the selected image is running and ready; a successful request submission is insufficient.
- Staging metadata must describe its own image. A production tag must not overwrite staging's version merely because production was released.
- Keep retained images available for manual Render rollback. Do not add a rollback workflow or require a new tag. Check the currently deployed image before starting a manual rollback so an already-running automated rollout does not immediately replace it.
- No automated database migration is introduced. Agents must not add, modify, or delete migration-version files. Database changes and recovery remain human-managed.

### Flutter environment selection

- Add a staging entry point and native staging flavor with the deployed staging URL as the default. Development and production keep their environment meanings, and API URL overrides remain available.
- Support the agreed staging entry point `main_staging.dart` with the `staging` flavor. Ordinary staging runs need no API URL argument.
- Use the existing development installation identity for staging on each platform unless a native constraint requires documenting an alternative before implementation. Do not introduce a new bundle identifier, Firebase project, OAuth registration, or requirement to install development and staging side by side solely for this feature.
- Align native schemes/build types, signing, Firebase options, OAuth callbacks, display configuration, and generated flavor configuration with the selected environment. A Dart-only entry point is not sufficient if the native flavor cannot build and authenticate.
- Record a monotonic integer build number for each platform and environment. Increment it for distributed builds; compare integers rather than semantic version strings, dates, or backend tags. An App build and an API image tag are separate identifiers.

### Policy contract and server enforcement

- Provide a stable, unauthenticated App support-policy lookup through the configured backend URL. Resolve the environment server-side, and select policy by a validated mobile platform. One environment's policy must not govern another environment.
- Publish the exact endpoint, platform/build header names, response schema, and machine-readable errors as a shared API contract before dependent Flutter work begins. Reuse the existing API response conventions and error envelope; successful response fields are camelCase with no success wrapper. Keep transport details in delivery and request context rather than duplicating them in feature services.
- Policy includes a non-negative integer minimum build and distribution-appropriate update guidance. Latest-build metadata is optional, and a newer available build must not force an update by itself. If latest is supplied, it cannot be lower than minimum.
- Supply update guidance suitable for both direct staging installs and eventual TestFlight/store distribution. Validate destinations before opening them. This spec does not require building a new store-release pipeline or optional-update campaign.
- Manage policy as validated operational configuration scoped to environment and platform. Document its source, update procedure, validation, and effective timing. A policy change must become observable by both lookup and request enforcement through the same policy source; no new database or admin UI is required by this spec.
- Apply request-level support enforcement at the shared App HTTP boundary, including anonymous feature reads and App authentication routes. Exempt policy discovery, public health, admin routes, and webhooks to avoid recovery loops and unrelated service disruption.
- Supported builds at or above the minimum retain normal authentication and feature behavior. Unsupported builds receive a stable update-required response before feature side effects occur. Use a distinct error from authentication expiry, validation failure, or backend unavailability.
- Flutter supplies platform/build identity on ordinary requests and handles the update-required error centrally. Do not implement a separate version gate in every feature repository, reuse auth-refresh responses for this purpose, or sign users out because an update is needed.
- During the initial compatible introduction, permit legacy requests without identity until policy-aware builds are available. Before enabling enforcement, explicitly configure and document rejection of missing, malformed, negative, or unsupported platform/build identities on gated routes. Unknown identity must not silently bypass an active gate. This is a compatibility control, not proof of a trustworthy client or an authentication mechanism.
- Keep policy discovery and update-required responses backward compatible for all builds expected to display the update screen. Already-distributed Apps without this capability need manual update instructions; the backend cannot remotely add it to those binaries.

### App behavior

- Use one App-wide support state with checking, supported, update-required, and connection/retry outcomes. Gate normal navigation and new feature requests while checking or blocked; keep this gate independent of onboarding completion and authentication status.
- Check at startup before normal API-dependent use and on return to the foreground. Route unsupported responses from already-running sessions to the same update UI. Coalesce simultaneous checks and avoid allowing a stale successful response to override a newer unsupported result.
- Only a successful valid policy comparison establishing that the installed build is below minimum shows forced-update messaging.
- Timeouts, unavailable services, malformed policy, and other unsuccessful policy checks show a connection/retry state and block normal use. A previously cached policy does not bypass a failed startup or foreground recheck. There is no offline grace period in this design.
- Retry performs a fresh check. A supported result resumes the App; an unsupported result shows update guidance; a failure remains retryable. Returning from an update destination also rechecks support.
- Use established iOS and Android presentation conventions and the App's existing supported locales. Do not clear sessions, reset onboarding, or discard persisted private drafts when displaying either blocked state.

### Rollout and ownership

- Introduce the compatible server policy contract, then distribute and verify policy-aware Flutter builds, then enable identity enforcement. Only after an installable compatible replacement exists may an operator raise a platform's minimum for a breaking backend rollout.
- Keep rollout steps explicit about ordering, effective policy values, in-progress App sessions, and human verification. A change that makes supported builds incompatible must not be deployed while its old support policy still admits them.
- Coordinate backend-image rollback, support-policy rollback, and database compatibility. Never lower the minimum in a way that admits an App incompatible with the rolled-back backend.
- This is one cross-repository specification owned by the Core API project. API policy/enforcement and release automation belong to the API repository; flavor configuration, build identity, lifecycle checks, and UI belong to the Flutter repository. Any later implementation tickets must each belong to one repository and declare cross-repository blockers.

## Testing Decisions

The user approved three external-behavior seams: the API HTTP boundary, assembled Flutter App journeys, and the release pipeline's tag-to-image-to-Render boundary. Prefer these to tests coupled to private helpers, individual state setters, file text, or every internal layer. Focus on results visible to callers and operators.

- **API HTTP seam:** reuse existing ASGI/HTTPX middleware-test patterns, real routing and serialization, and injected configuration/providers. Existing router contract tests and middleware consumer tests provide prior art; add request-through-middleware coverage rather than relying only on direct handler calls. Assert response status/body and absence of downstream side effects for rejected requests.
- Exercise below-minimum, equal-minimum, above-minimum, newer-than-latest, iOS/Android separation, environment isolation, policy retrieval without login, legacy introduction mode, active enforcement of missing/invalid identity, anonymous/authenticated traffic, and all exempt surfaces. Verify invalid policy is not represented as a valid outdated-App decision.
- **Flutter App seam:** reuse assembled App/router journey tests with existing fake repositories and fake HTTP adapters. Assert the screen and enabled actions for startup, resume, request-level rejection, update return, and retry transitions. Verify an unsupported response from several concurrent requests results in one blocking state, not repeated navigation or auth-refresh loops.
- Exercise network timeout, unavailable backend, malformed policy, cached-policy plus failed recheck, successful recovery, equal/above-minimum acceptance, no mandatory update solely because latest is newer, and preservation of session/draft state. Use the existing shared API-client fake-adapter tests only where needed to verify emitted client identity and error classification that App journeys cannot observe clearly.
- Verify staging defaults and intentional overrides through public configuration behavior. A native iOS and Android build must resolve the staging flavor, target entry point, and intended installation identity without the repeated URL argument. Real-device checks cover signing, OAuth, Firebase, lifecycle transitions, localization, and update destinations.
- **Release boundary:** there is no existing comprehensive staging deployment harness. Introduce one focused harness that exercises release orchestration against fake registry/Render clients and temporary Git history. Reuse the repository's shell-test approach where useful. Assert selected commits, published tags, external requests, and completion/failure results rather than mirroring YAML text.
- Cover main merges causing no image build or deploy; valid staging tags; malformed/date-invalid tags; unmerged commits; allowed historical main commits; existing-artifact retry; failed checks/build/publish; failed Render calls; concurrent deployment serialization; readiness failure; and production release events leaving staging metadata unchanged.
- Human live acceptance records an actual tag deployment, health/image verification, a later main merge leaving staging unchanged, a manual Render rollback to the same retained image, and policy behavior on real supported/unsupported App builds. Offline tests do not establish Render deployment or device acceptance.

## Out of Scope

- Implementing or deploying this feature as part of publishing the spec, creating implementation tickets, or committing/pushing repository changes.
- Redesigning production deployment, adding approval stages, release branches, preview environments, or another backend service.
- An Actions rollback workflow, new rollback tags, or rebuilding an old image to recover.
- A new bundle identifier or side-by-side installation requirement for staging.
- Permanent support for every historical beta, exact App/API commit equality, or forcing updates whenever latest differs.
- Database migration automation, changes under migration-version directories, and automatic schema/data rollback.
- An offline bypass for failed policy checks, a new admin policy-management UI, a new App-store distribution pipeline, or binary self-updates.
- Changes to devotion, Bible, private Journal, Fellowship, authentication semantics, or privacy rules beyond the shared support gate.

## Further Notes

Published as [GitHub #162](https://github.com/rooted-faith/rooted-core-api/issues/162), synchronized to [ROO-161](https://linear.app/jayhsia/issue/ROO-161/spec-tag-selected-staging-releases-and-minimum-supported-app-builds) in the rooted core api project. The published spec remains in Backlog with spec and ready-for-agent labels.

The accepted design is recorded in ADR 0017. Current repository evidence shows main-triggered GHCR/Render staging deployment, a separate production-tag workflow that also mutates staging version metadata, Flutter development/production flavors with a build-time URL override, and no existing App support-policy gate. These are repository findings, not live deployment verification.

The owner currently installs release-mode development builds directly on a physical iPhone with an explicit staging URL. The staging flavor removes that repeated argument. When staging shares the development installation identity, installing one can replace the other; side-by-side installation is not a requirement.

The API URL remains stable while the operator-selected image changes. Minimum-build enforcement deliberately bounds compatibility; it does not make incompatible schema changes or prematurely published update requirements safe. Freeze acceptance by withholding another staging tag, and record App build, backend image, policy values, and migration prerequisites together.
