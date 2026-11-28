#!/usr/bin/env bash
# Black-box tests for scripts/staging-release-target.sh against a throwaway Git repository.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${ROOT_DIR}/scripts/staging-release-target.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

pass_count=0
fail_count=0

git init -q -b main "${WORK}/origin"
git -C "${WORK}/origin" -c user.name=t -c user.email=t@example.com commit -q --allow-empty -m base
HISTORICAL_SHA="$(git -C "${WORK}/origin" rev-parse HEAD)"
git -C "${WORK}/origin" -c user.name=t -c user.email=t@example.com commit -q --allow-empty -m later-main
git -C "${WORK}/origin" checkout -q -b topic
git -C "${WORK}/origin" -c user.name=t -c user.email=t@example.com commit -q --allow-empty -m unmerged
UNMERGED_SHA="$(git -C "${WORK}/origin" rev-parse HEAD)"
git -C "${WORK}/origin" checkout -q main
git clone -q "${WORK}/origin" "${WORK}/clone"
REPO="${WORK}/clone"
MAIN_SHA="$(git -C "${REPO}" rev-parse origin/main)"

run_target() {
  set +e
  output="$(cd "${REPO}" && "${TARGET}" "$@" 2>&1)"
  actual_exit=$?
  set -e
}

assert_target() {
  local label="$1" expected_exit="$2" expected="$3"
  shift 3
  run_target "$@"
  if [[ "${actual_exit}" -ne "${expected_exit}" || "${output}" != *"${expected}"* ]]; then
    fail_count=$((fail_count + 1))
    echo "FAIL: ${label}"
    echo "  expected exit ${expected_exit} with: ${expected}"
    echo "  got exit ${actual_exit}: ${output}"
    return
  fi
  pass_count=$((pass_count + 1))
}

assert_target "main does not publish" 0 "publish=false" branch main "${MAIN_SHA}"
assert_target "topic branch does not publish" 0 "publish=false" branch feat/roo-162-x "${MAIN_SHA}"

valid_out="publish=true
image_tag=stg.261128.1
release=stg.261128.1
revision=${MAIN_SHA}"
assert_target "valid staging tag on main publishes" 0 "${valid_out}" tag stg.261128.1 "${MAIN_SHA}"

historical_out="publish=true
image_tag=stg.261128.2
release=stg.261128.2
revision=${HISTORICAL_SHA}"
assert_target "historical main commit is allowed" 0 "${historical_out}" tag stg.261128.2 "${HISTORICAL_SHA}"

assert_target "unmerged commit is refused" 1 "not reachable from origin/main" tag stg.261128.3 "${UNMERGED_SHA}"
assert_target "malformed tag is refused" 1 "not a valid staging release tag" tag stg.261128 "${MAIN_SHA}"
assert_target "zero sequence is refused" 1 "not a valid staging release tag" tag stg.261128.0 "${MAIN_SHA}"
assert_target "leading-zero sequence is refused" 1 "not a valid staging release tag" tag stg.261128.01 "${MAIN_SHA}"
assert_target "invalid calendar date is refused" 1 "not a valid calendar date" tag stg.261332.1 "${MAIN_SHA}"
assert_target "invalid February date is refused" 1 "not a valid calendar date" tag stg.260230.1 "${MAIN_SHA}"
assert_target "production tag is refused" 1 "not a valid staging release tag" tag v1.2.3 "${MAIN_SHA}"
assert_target "short SHA is refused" 1 "full 40-character commit SHA" tag stg.261128.1 "${MAIN_SHA:0:12}"
assert_target "unknown ref type is refused" 1 "Usage:" pull stg.261128.1 "${MAIN_SHA}"

if [[ "${fail_count}" -gt 0 ]]; then
  echo "${fail_count} failed, ${pass_count} passed"
  exit 1
fi

echo "All ${pass_count} checks passed"
