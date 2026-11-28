#!/usr/bin/env bash
# Contract: production release automation must not rewrite staging-only VERSION metadata (ADR 0017).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELEASE_WORKFLOW="${ROOT_DIR}/.github/workflows/release.yml"
CI_WORKFLOW="${ROOT_DIR}/.github/workflows/ci.yml"
STAGING_DEPLOY="${ROOT_DIR}/scripts/deploy-staging-render.sh"

pass_count=0
fail_count=0

check() {
  local label="$1"
  shift
  if "$@"; then
    pass_count=$((pass_count + 1))
  else
    fail_count=$((fail_count + 1))
    echo "FAIL: ${label}"
  fi
}

check "production workflow exists" test -f "${RELEASE_WORKFLOW}"
check "production workflow still updates prod VERSION" \
  grep -q 'secrets.RENDER_ENVIRONMENT_PROD_ID }}/env-vars/VERSION' "${RELEASE_WORKFLOW}"
check "production workflow does not reference staging env group" \
  bash -c "! grep -q 'RENDER_ENVIRONMENT_STG_ID' '${RELEASE_WORKFLOW}'"
check "staging VERSION is owned by staging deploy script" \
  grep -q '/env-groups/${env_group_id}/env-vars/VERSION' "${STAGING_DEPLOY}"
check "main CI workflow exists" test -f "${CI_WORKFLOW}"
check "main CI does not build container images" \
  bash -c "! grep -Eqi 'docker (build|buildx|push)|build-push-action|setup-buildx' '${CI_WORKFLOW}'"
check "main CI does not call Render" \
  bash -c "! grep -Eqi 'api.render.com|RENDER_SERVICE_ID|deploy-staging' '${CI_WORKFLOW}'"
check "main CI does not publish to GHCR" \
  bash -c "! grep -Eqi 'ghcr-publish|docker/login-action' '${CI_WORKFLOW}'"

if [[ "${fail_count}" -gt 0 ]]; then
  echo "${fail_count} failed, ${pass_count} passed"
  exit 1
fi

echo "All ${pass_count} checks passed"
