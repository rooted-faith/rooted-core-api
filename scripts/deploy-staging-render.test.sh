#!/usr/bin/env bash
# Black-box tests for scripts/deploy-staging-render.sh with fake curl on PATH. Never contacts Render.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY="${ROOT_DIR}/scripts/deploy-staging-render.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

IMAGE="ghcr.io/rooted-faith/rooted-core-api@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
OLD_IMAGE="ghcr.io/rooted-faith/rooted-core-api@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
RELEASE="stg.261128.1"

pass_count=0
fail_count=0

mkdir -p "${WORK}/bin"
cat >"${WORK}/bin/curl" <<'EOF'
#!/usr/bin/env bash
echo "curl $*" >>"$FAKE_LOG"
state_dir="$(dirname "$FAKE_LOG")"

method="GET"
url=""
prev=""
for arg in "$@"; do
  if [[ "${prev}" == "-X" || "${prev}" == "--request" ]]; then
    method="${arg}"
  elif [[ "${arg}" == https://* ]]; then
    url="${arg}"
  fi
  prev="${arg}"
done

if [[ "${url}" == *"/healthz" ]]; then
  count=$(( $(cat "${state_dir}/curl-health-count" 2>/dev/null || echo 0) + 1 ))
  echo "$count" >"${state_dir}/curl-health-count"
  if (( count > ${FAKE_HEALTH_FAILS:-0} )); then
    exit 0
  fi
  exit 22
fi

if [[ -n "${FAKE_FAIL:-}" && ( "${method}" == "${FAKE_FAIL}" || "${url}" == *"${FAKE_FAIL}"* ) ]]; then
  echo '{"message":"fake failure"}' >&2
  exit 1
fi

if [[ "${method}" == "GET" && "${url}" == *"/deploys/"* ]]; then
  count=$(( $(cat "${state_dir}/poll-count" 2>/dev/null || echo 0) + 1 ))
  echo "$count" >"${state_dir}/poll-count"
  if (( count <= ${FAKE_DEPLOY_PENDING_POLLS:-0} )); then
    echo '{"id":"dep-new","status":"update_in_progress"}'
  else
    echo "{\"id\":\"dep-new\",\"status\":\"${FAKE_DEPLOY_STATUS:-live}\"}"
  fi
  exit 0
fi

if [[ "${method}" == "GET" && "${url}" == *"/deploys"* ]]; then
  count=$(( $(cat "${state_dir}/active-polls" 2>/dev/null || echo 0) + 1 ))
  echo "$count" >"${state_dir}/active-polls"
  if (( count <= ${FAKE_ACTIVE_DEPLOY_POLLS:-0} )); then
    echo '[{"deploy":{"id":"dep-old","status":"update_in_progress"}}]'
  else
    echo '[{"deploy":{"id":"dep-old","status":"live"}}]'
  fi
  exit 0
fi

if [[ "${method}" == "POST" && "${url}" == *"/deploys" ]]; then
  echo '{"id":"dep-new","status":"created"}'
  exit 0
fi

if [[ "${method}" == "PATCH" && "${url}" == *"/services/"* ]]; then
  if [[ -n "${IMAGE_AFTER_PATCH:-}" ]]; then
    echo "${IMAGE_AFTER_PATCH}" >"${state_dir}/service-image"
  else
    echo "${WANTED_IMAGE}" >"${state_dir}/service-image"
  fi
  echo '{"id":"srv-stg"}'
  exit 0
fi

if [[ "${method}" == "PUT" && "${url}" == *"/env-vars/VERSION"* ]]; then
  echo "${url}" >>"${state_dir}/version-writes"
  echo '{"key":"VERSION"}'
  exit 0
fi

if [[ "${method}" == "GET" && "${url}" == *"/services/"* ]]; then
  img="$(cat "${state_dir}/service-image" 2>/dev/null || echo "${FAKE_SERVICE_IMAGE}")"
  echo "{\"image\":{\"imagePath\":\"${img}\"}}"
  exit 0
fi

echo "{}"
exit 0
EOF
chmod +x "${WORK}/bin/curl"

run_deploy() {
  export FAKE_LOG="${WORK}/calls.log"
  : >"${FAKE_LOG}"
  rm -f "${WORK}/poll-count" "${WORK}/active-polls" "${WORK}/curl-health-count" \
    "${WORK}/service-image" "${WORK}/version-writes"
  set +e
  output="$(
    PATH="${WORK}/bin:${PATH}" \
      RENDER_API_KEY=rk \
      RENDER_SERVICE_ID=srv-stg \
      RENDER_OWNER_ID=own \
      RENDER_REGISTRY_CREDENTIAL_ID=cred \
      RENDER_ENVIRONMENT_STG_ID=evg-stg \
      STAGING_URL=https://api-stg.example.test \
      WANTED_IMAGE="${IMAGE}" \
      FAKE_SERVICE_IMAGE="${OLD_IMAGE}" \
      POLL_INTERVAL=0 \
      ACTIVE_WAIT_INTERVAL=0 \
      SMOKE_DELAY=0 \
      SMOKE_INTERVAL=0 \
      SMOKE_TRIES=3 \
      "${DEPLOY}" "${IMAGE}" "${RELEASE}" 2>&1
  )"
  actual_exit=$?
  set -e
  calls="$(cat "${FAKE_LOG}")"
}

check() {
  local label="$1"
  shift
  if "$@"; then
    pass_count=$((pass_count + 1))
  else
    fail_count=$((fail_count + 1))
    echo "FAIL: ${label}"
    echo "  exit ${actual_exit}, output: ${output}"
    echo "  calls: ${calls}"
  fi
}
has() { [[ "$1" == *"$2"* ]]; }
lacks() { [[ "$1" != *"$2"* ]]; }

run_deploy
check "deploy exits 0" test "${actual_exit}" -eq 0
check "deploy lists deploys before mutating" has "${calls}" "/deploys?limit=1"
check "deploy patches service image" has "${calls}" "--request PATCH"
check "deploy triggers a new deploy" has "${calls}" "--request POST"
check "deploy writes staging VERSION" has "${calls}" "/env-groups/evg-stg/env-vars/VERSION"
check "deploy records previous image" has "${output}" "previous_image=${OLD_IMAGE}"
check "deploy reports smoke passed" has "${output}" "smoke=passed"
check "deploy checks healthz" has "${calls}" "https://api-stg.example.test/healthz"

FAKE_ACTIVE_DEPLOY_POLLS=2 run_deploy
check "active rollout is waited out before patch" test "${actual_exit}" -eq 0
check "active rollout polled more than once" test "$(cat "${WORK}/active-polls")" -ge 2
patch_line="$(grep -n -- '--request PATCH' <<<"${calls}" | head -1 | cut -d: -f1)"
first_active_line="$(grep -n '/deploys?limit=1' <<<"${calls}" | head -1 | cut -d: -f1)"
check "active wait happens before patch" test "${first_active_line}" -lt "${patch_line}"

FAKE_DEPLOY_PENDING_POLLS=2 run_deploy
check "new deploy is polled to completion" test "${actual_exit}" -eq 0
check "new deploy polled more than once" test "$(cat "${WORK}/poll-count")" -ge 2

FAKE_DEPLOY_STATUS=update_failed run_deploy
check "failed deploy status fails" test "${actual_exit}" -ne 0
check "failed deploy status explains" has "${output}" "update_failed"

FAKE_FAIL=PATCH run_deploy
check "failed Render patch fails" test "${actual_exit}" -ne 0
check "failed Render patch does not POST deploy" lacks "${calls}" "--request POST"

FAKE_FAIL=POST run_deploy
check "failed Render deploy request fails" test "${actual_exit}" -ne 0

FAKE_HEALTH_FAILS=999 run_deploy
check "readiness failure fails" test "${actual_exit}" -ne 0
check "readiness failure reports" has "${output}" "smoke=failed"

IMAGE_AFTER_PATCH="${OLD_IMAGE}" run_deploy
check "wrong running image fails" test "${actual_exit}" -ne 0
check "wrong running image explains" has "${output}" "still runs"

set +e
usage_out="$(
  PATH="${WORK}/bin:${PATH}" RENDER_API_KEY=rk RENDER_SERVICE_ID=s RENDER_OWNER_ID=o \
    RENDER_REGISTRY_CREDENTIAL_ID=c RENDER_ENVIRONMENT_STG_ID=e STAGING_URL=https://x \
    "${DEPLOY}" "${IMAGE}" 2>&1
)"
usage_exit=$?
set -e
check "missing release prints usage" has "${usage_out}" "Usage:"
check "missing release exits non-zero" test "${usage_exit}" -ne 0

if [[ "${fail_count}" -gt 0 ]]; then
  echo "${fail_count} failed, ${pass_count} passed"
  exit 1
fi

echo "All ${pass_count} checks passed"
