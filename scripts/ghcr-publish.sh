#!/usr/bin/env bash
# Publish a locally built image to GHCR under an immutable staging tag (ADR 0017).
#   - The local image's org.opencontainers.image.revision label must equal <revision>.
#   - A tag that already exists is never overwritten. Matching revision digests are reused.
# Prints key=value lines for $GITHUB_OUTPUT: digest, image (digest reference), reused.
#
# Usage: ghcr-publish.sh <local-image> <image-tag> <revision>
#   REGISTRY=ghcr.io IMAGE_NAME=<owner/repo> REGISTRY_USER=... REGISTRY_TOKEN=...
set -euo pipefail

local_image="${1:-}"
tag="${2:-}"
revision="${3:-}"
registry="${REGISTRY:-ghcr.io}"
image_name="${IMAGE_NAME:-}"
remote="${registry}/${image_name}"

if [[ -z "${local_image}" || -z "${tag}" || -z "${revision}" || -z "${image_name}" ]]; then
  echo "Usage: $0 <local-image> <image-tag> <revision> (requires IMAGE_NAME)" >&2
  exit 1
fi
if [[ -z "${REGISTRY_USER:-}" || -z "${REGISTRY_TOKEN:-}" ]]; then
  echo "REGISTRY_USER and REGISTRY_TOKEN are required" >&2
  exit 1
fi

revision_label='{{ index .Config.Labels "org.opencontainers.image.revision" }}'
local_revision="$(docker image inspect --format "${revision_label}" "${local_image}")"
if [[ "${local_revision}" != "${revision}" ]]; then
  echo "${local_image} has revision label ${local_revision}, expected ${revision}" >&2
  exit 1
fi

probe_remote_tag() {
  # Prints: missing | exists <revision> <digest> | error <message>
  local inspect_out
  local inspect_code
  set +e
  inspect_out="$(docker buildx imagetools inspect "${remote}:${tag}" \
    --format '{{ index .Image.Config.Labels "org.opencontainers.image.revision" }} {{.Manifest.Digest}}' 2>&1)"
  inspect_code=$?
  set -e
  if [[ "${inspect_code}" -eq 0 ]]; then
    echo "exists ${inspect_out}"
    return 0
  fi
  if [[ "${inspect_out}" == *"not found"* || "${inspect_out}" == *"NotFound"* || "${inspect_out}" == *"NAME_UNKNOWN"* ]]; then
    echo "missing"
    return 0
  fi
  echo "error ${inspect_out}"
  return 0
}

probe="$(probe_remote_tag)"
case "${probe}" in
  missing)
    echo "${REGISTRY_TOKEN}" | docker login "${registry}" -u "${REGISTRY_USER}" --password-stdin >/dev/null
    docker tag "${local_image}" "${remote}:${tag}"
    docker push "${remote}:${tag}" >/dev/null
    probe="$(probe_remote_tag)"
    if [[ "${probe}" != exists\ * ]]; then
      echo "Published ${remote}:${tag} but could not resolve its digest (${probe})" >&2
      exit 1
    fi
    digest="${probe##* }"
    reused=false
    ;;
  exists\ *)
    # shellcheck disable=SC2086
    set -- ${probe}
    # $1=exists $2=revision $3=digest
    remote_revision="${2}"
    digest="${3}"
    if [[ "${remote_revision}" != "${revision}" ]]; then
      echo "${remote}:${tag} already exists for revision ${remote_revision}; refusing to overwrite it with ${revision}" >&2
      exit 1
    fi
    reused=true
    ;;
  error\ *)
    echo "Failed to determine whether ${remote}:${tag} already exists: ${probe#error }" >&2
    exit 1
    ;;
  *)
    echo "Unexpected registry probe result: ${probe}" >&2
    exit 1
    ;;
esac

if [[ ! "${digest}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "Could not resolve digest for ${remote}:${tag}" >&2
  exit 1
fi

cat <<EOF
digest=${digest}
image=${remote}@${digest}
reused=${reused}
EOF
