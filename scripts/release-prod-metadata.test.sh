#!/usr/bin/env bash
# Contract: production release automation must not rewrite staging-only VERSION metadata (ADR 0017).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELEASE_WORKFLOW="${ROOT_DIR}/.github/workflows/release.yml"
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
  grep -q 'RENDER_ENVIRONMENT_PROD_ID.*/env-vars/VERSION\|env-groups/\${{ secrets.RENDER_ENVIRONMENT_PROD_ID }}/env-vars/VERSION' "${RELEASE_WORKFLOW}"
check "production workflow does not write staging VERSION" \
  grep -vq 'RENDER_ENVIRONMENT_STG_ID' "${RELEASE_WORKFLOW}"
check "staging VERSION is owned by staging deploy script" \
  grep -q 'env-groups/\${env_group_id}/env-vars/VERSION\|/env-groups/.*/env-vars/VERSION' "${STAGING_DEPLOY}"

if [[ "${fail_count}" -gt 0 ]]; then
  echo "${fail_count} failed, ${pass_count} passed"
  exit 1
fi

echo "All ${pass_count} checks passed"
