#!/usr/bin/env bash
# Black-box tests for scripts/ghcr-publish.sh with fake docker on PATH. Never contacts GHCR.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUBLISH="${ROOT_DIR}/scripts/ghcr-publish.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

REV="1111111111111111111111111111111111111111"
OTHER="2222222222222222222222222222222222222222"
DIGEST="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
IMAGE_NAME="rooted-faith/rooted-core-api"

pass_count=0
fail_count=0

mkdir -p "${WORK}/bin"
cat >"${WORK}/bin/docker" <<'EOF'
#!/usr/bin/env bash
echo "docker $*" >>"$FAKE_LOG"
state_dir="$(dirname "$FAKE_LOG")"
[[ -n "${FAKE_FAIL:-}" && "$*" == *"${FAKE_FAIL}"* ]] && { echo "fake failure" >&2; exit 1; }
case "$*" in
  "image inspect"*) echo "${FAKE_LOCAL_REV}" ;;
  "login"*) ;;
  "tag "*) ;;
  "push "*)
    echo "${FAKE_LOCAL_REV}" >"${state_dir}/remote-rev"
    echo "${FAKE_REMOTE_DIGEST:-sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa}" \
      >"${state_dir}/remote-digest"
    ;;
  "buildx imagetools inspect"*)
    if [[ -f "${state_dir}/remote-rev" ]]; then
      echo "$(cat "${state_dir}/remote-rev") $(cat "${state_dir}/remote-digest")"
      exit 0
    fi
    if [[ "${FAKE_REMOTE_MISSING:-}" == "1" ]]; then
      echo "not found" >&2
      exit 1
    fi
    if [[ -n "${FAKE_REMOTE_REV:-}" ]]; then
      echo "${FAKE_REMOTE_REV} ${FAKE_REMOTE_DIGEST:-sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa}"
      exit 0
    fi
    echo "not found" >&2
    exit 1
    ;;
esac
EOF
chmod +x "${WORK}/bin/docker"

run_publish() {
  export FAKE_LOG="${WORK}/calls.log"
  : >"${FAKE_LOG}"
  rm -f "${WORK}/remote-rev" "${WORK}/remote-digest"
  set +e
  output="$(
    PATH="${WORK}/bin:${PATH}" \
      REGISTRY=ghcr.io \
      IMAGE_NAME="${IMAGE_NAME}" \
      REGISTRY_USER=u \
      REGISTRY_TOKEN=t \
      "${PUBLISH}" "$@" 2>&1
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

FAKE_REMOTE_MISSING=1 FAKE_LOCAL_REV="${REV}" run_publish rooted-core-api:ci stg.261128.1 "${REV}"
check "new tag exits 0" test "${actual_exit}" -eq 0
check "new tag logs in" has "${calls}" "docker login ghcr.io"
check "new tag pushes" has "${calls}" "docker push ghcr.io/${IMAGE_NAME}:stg.261128.1"
check "new tag prints digest" has "${output}" "digest=${DIGEST}"
check "new tag prints image ref" has "${output}" "image=ghcr.io/${IMAGE_NAME}@${DIGEST}"
check "new tag is not reused" has "${output}" "reused=false"

FAKE_REMOTE_MISSING= FAKE_REMOTE_REV="${REV}" FAKE_REMOTE_DIGEST="${DIGEST}" FAKE_LOCAL_REV="${REV}" \
  run_publish rooted-core-api:ci stg.261128.1 "${REV}"
check "rerun exits 0" test "${actual_exit}" -eq 0
check "rerun does not push" lacks "${calls}" "docker push"
check "rerun reuses" has "${output}" "reused=true"
check "rerun prints digest" has "${output}" "digest=${DIGEST}"

FAKE_REMOTE_REV="${OTHER}" FAKE_LOCAL_REV="${REV}" run_publish rooted-core-api:ci stg.261128.1 "${REV}"
check "foreign tag fails" test "${actual_exit}" -ne 0
check "foreign tag is not pushed" lacks "${calls}" "docker push"
check "foreign tag explains" has "${output}" "already exists for revision ${OTHER}"

FAKE_REMOTE_MISSING=1 FAKE_LOCAL_REV="${OTHER}" run_publish rooted-core-api:ci stg.261128.1 "${REV}"
check "label mismatch fails" test "${actual_exit}" -ne 0
check "label mismatch does not log in" lacks "${calls}" "docker login"
check "label mismatch explains" has "${output}" "revision label ${OTHER}"

FAKE_FAIL="imagetools inspect" FAKE_LOCAL_REV="${REV}" run_publish rooted-core-api:ci stg.261128.1 "${REV}"
check "inspect failure fails closed" test "${actual_exit}" -ne 0
check "inspect failure does not push" lacks "${calls}" "docker push"

FAKE_REMOTE_MISSING=1 FAKE_FAIL="push" FAKE_LOCAL_REV="${REV}" \
  run_publish rooted-core-api:ci stg.261128.1 "${REV}"
check "push failure fails" test "${actual_exit}" -ne 0

FAKE_LOCAL_REV="${REV}" run_publish rooted-core-api:ci stg.261128.1
check "missing revision fails with usage" has "${output}" "Usage:"

if [[ "${fail_count}" -gt 0 ]]; then
  echo "${fail_count} failed, ${pass_count} passed"
  exit 1
fi

echo "All ${pass_count} checks passed"
