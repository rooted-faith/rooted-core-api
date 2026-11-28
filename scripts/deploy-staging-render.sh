#!/usr/bin/env bash
# Point the staging Render service at a published image digest, set VERSION, wait for the
# asynchronous deploy to finish, verify image identity, then smoke-test /healthz (ADR 0017).
# Waits for any in-progress deploy before starting another. Does not cancel active rollouts.
# A failed smoke or status check is reported; there is no automatic rollback.
#
# Usage: deploy-staging-render.sh <registry>/<image>@sha256:<digest> <stg.YYMMDD.N>
#   RENDER_API_KEY RENDER_SERVICE_ID RENDER_OWNER_ID RENDER_REGISTRY_CREDENTIAL_ID
#   RENDER_ENVIRONMENT_STG_ID STAGING_URL
#   POLL_INTERVAL ACTIVE_WAIT_INTERVAL SMOKE_DELAY SMOKE_TRIES SMOKE_INTERVAL (seconds)
set -euo pipefail

image="${1:-}"
release="${2:-}"
api_key="${RENDER_API_KEY:-}"
service_id="${RENDER_SERVICE_ID:-}"
owner_id="${RENDER_OWNER_ID:-}"
credential_id="${RENDER_REGISTRY_CREDENTIAL_ID:-}"
env_group_id="${RENDER_ENVIRONMENT_STG_ID:-}"
url="${STAGING_URL:-}"
poll_interval="${POLL_INTERVAL:-10}"
active_wait_interval="${ACTIVE_WAIT_INTERVAL:-10}"
api_base="https://api.render.com/v1"

if [[ -z "${image}" || -z "${release}" ]]; then
  echo "Usage: $0 <registry>/<image>@sha256:<digest> <stg.YYMMDD.N>" >&2
  exit 1
fi
if [[ ! "${image}" =~ ^[a-z0-9./_-]+@sha256:[0-9a-f]{64}$ ]]; then
  echo "${image} is not a digest reference" >&2
  exit 1
fi
if [[ ! "${release}" =~ ^stg\.[0-9]{6}\.[1-9][0-9]*$ ]]; then
  echo "${release} is not a staging release tag" >&2
  exit 1
fi
if [[ -z "${api_key}" || -z "${service_id}" || -z "${owner_id}" || -z "${credential_id}" || -z "${env_group_id}" || -z "${url}" ]]; then
  echo "RENDER_API_KEY, RENDER_SERVICE_ID, RENDER_OWNER_ID, RENDER_REGISTRY_CREDENTIAL_ID, RENDER_ENVIRONMENT_STG_ID, and STAGING_URL are required" >&2
  exit 1
fi

auth_header=("Authorization: Bearer ${api_key}")

render_curl() {
  local method="$1"
  local path="$2"
  shift 2
  curl --silent --show-error --fail-with-body \
    --request "${method}" \
    --header "${auth_header[0]}" \
    --header "Accept: application/json" \
    "$@" \
    "${api_base}${path}"
}

service_image_path() {
  render_curl GET "/services/${service_id}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("image",{}).get("imagePath",""))'
}

deploy_status() {
  local deploy_id="$1"
  render_curl GET "/services/${service_id}/deploys/${deploy_id}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status",""))'
}

latest_deploy_status() {
  render_curl GET "/services/${service_id}/deploys?limit=1" | python3 -c '
import json,sys
rows=json.load(sys.stdin)
if not rows:
  print("")
  raise SystemExit(0)
item=rows[0]
deploy=item.get("deploy", item)
print(deploy.get("status",""))
'
}

is_in_progress() {
  case "$1" in
    created|queued|build_in_progress|update_in_progress|pre_deploy_in_progress) return 0 ;;
    *) return 1 ;;
  esac
}

wait_for_idle_service() {
  local status
  while true; do
    status="$(latest_deploy_status)"
    if [[ -z "${status}" ]] || ! is_in_progress "${status}"; then
      return 0
    fi
    echo "waiting_for_active_deploy status=${status}" >&2
    sleep "${active_wait_interval}"
  done
}

wait_for_deploy() {
  local deploy_id="$1"
  local status=""
  while true; do
    status="$(deploy_status "${deploy_id}")"
    if is_in_progress "${status}"; then
      echo "waiting_for_deploy id=${deploy_id} status=${status}" >&2
      sleep "${poll_interval}"
      continue
    fi
    if [[ "${status}" == "live" ]]; then
      echo "deploy_status=live"
      return 0
    fi
    echo "deploy_status=${status}"
    echo "Render deploy ${deploy_id} ended with status ${status}" >&2
    return 1
  done
}

previous="$(service_image_path)"
echo "previous_image=${previous}"

wait_for_idle_service

payload="$(
  OWNER_ID="${owner_id}" CREDENTIAL_ID="${credential_id}" IMAGE_PATH="${image}" python3 -c '
import json,os
print(json.dumps({
  "image": {
    "ownerId": os.environ["OWNER_ID"],
    "registryCredentialId": os.environ["CREDENTIAL_ID"],
    "imagePath": os.environ["IMAGE_PATH"],
  }
}))
'
)"
render_curl PATCH "/services/${service_id}" \
  --header "Content-Type: application/json" \
  --data "${payload}" >/dev/null

version_payload="$(RELEASE="${release}" python3 -c 'import json,os; print(json.dumps({"value": os.environ["RELEASE"]}))')"
render_curl PUT "/env-groups/${env_group_id}/env-vars/VERSION" \
  --header "Content-Type: application/json" \
  --data "${version_payload}" >/dev/null

deploy_json="$(render_curl POST "/services/${service_id}/deploys" --header "Content-Type: application/json" --data '{}')"
deploy_id="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"${deploy_json}")"
echo "deploy_id=${deploy_id}"

wait_for_deploy "${deploy_id}"

running="$(service_image_path)"
if [[ "${running}" != "${image}" && "${running}" != *"${image#*@}"* ]]; then
  echo "${service_id} still runs ${running}, expected ${image}" >&2
  exit 1
fi
echo "running_image=${running}"

sleep "${SMOKE_DELAY:-15}"
tries="${SMOKE_TRIES:-20}"
for ((i = 1; i <= tries; i++)); do
  if curl --fail --silent --show-error --max-time 10 --output /dev/null "${url}/healthz"; then
    echo "smoke=passed"
    exit 0
  fi
  ((i < tries)) && sleep "${SMOKE_INTERVAL:-15}"
done

echo "smoke=failed"
echo "${url}/healthz did not answer 200 after ${tries} tries. No automatic rollback; previous image: ${previous}" >&2
exit 1
