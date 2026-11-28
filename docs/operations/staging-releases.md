# Staging releases

Operator runbook for selecting and rolling back staging API images (ADR 0017 / ROO-162). Live deployment acceptance belongs to a later human rollout ticket; this document describes the repository automation and manual Render recovery.

## What main does

Pushes and merges to `main` run repository checks only (`CI` workflow). They do **not** build a container image and do **not** change the running staging service.

## Select a staging release

1. Choose a commit that is already on `main` (latest or historical). Unmerged commits are rejected before any registry or Render mutation.
2. Pick the next unused tag for that UTC calendar day: `stg.YYMMDD.N`
   - `YYMMDD` must be a real calendar date (example: `stg.261128.1` for 2026-11-28).
   - `N` is a positive integer starting at `1` each day (`1`, `2`, … — no leading zeros).
3. Create and push the tag on that commit:

   ```bash
   git tag stg.261128.1 <commit-sha>
   git push origin stg.261128.1
   ```

4. The tag push is the deploy authorization. There is no second Actions approval, freeze switch, or extra staging service.
5. The `Staging Release` workflow validates the tag, runs checks, builds the selected commit, publishes `ghcr.io/<org>/<repo>:stg.YYMMDD.N`, and deploys that digest to Render. Published tags/images are not overwritten; a workflow retry reuses the same artifact when the revision matches.
6. Record acceptance with: App build (if applicable), API URL `https://api-stg.rootedfaith.app`, backend image tag/digest from the workflow summary, and any migration prerequisites.

Failed validation, checks, build, publication, Render requests, deploy status, or `/healthz` readiness leave a successful result unset. An in-progress automated rollout is never cancelled to start another; workflows share a concurrency group that waits through completion.

## Staging VERSION metadata

Staging `VERSION` is set to the selected `stg.YYMMDD.N` tag during that staging deploy. Production `v*.*.*` releases update production `VERSION` only and must not rewrite staging metadata.

## Retained images and manual rollback

Published staging images remain in GHCR for reuse. Rollback does **not** use a new tag, a rebuild, or an Actions rollback workflow.

1. In the Render dashboard, open the staging service.
2. Confirm whether an automated rollout is already in progress. If one is running, wait for it to finish (or fail) before changing the image so the automation does not immediately replace your selection.
3. Select a previously retained image (the prior `stg.*` digest) and deploy it.
4. Confirm `/healthz` and that the service image identity matches the retained digest you chose.
5. If you also need the staging `VERSION` env var to match the rolled-back tag for operator clarity, update that env-group value manually in Render.

## Database and policy compatibility

- Agents and workflows do **not** run migrations. Apply or reverse schema/data changes by hand before claiming a release or rollback is usable.
- A container rollback requires compatible database state. Coordinate backend image, support-policy values (when present), and database recovery so a lowered App minimum never admits a client incompatible with the selected image.
- Freezing acceptance means withholding another staging tag, not relying on `main` to stay quiet.

## Related automation

| Path | Role |
| --- | --- |
| `scripts/staging-release-target.sh` | Tag syntax, calendar date, main ancestry |
| `scripts/ghcr-publish.sh` | Immutable GHCR publish / same-revision reuse |
| `scripts/deploy-staging-render.sh` | Render image select, deploy wait, identity + readiness |
| `.github/workflows/ci.yml` | Checks on PRs and `main` |
| `.github/workflows/staging-release.yml` | Tag-triggered build/publish/deploy |
| `.github/workflows/release.yml` | Production tags (`v*.*.*`) without staging VERSION writes |
