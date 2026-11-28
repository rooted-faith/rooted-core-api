#!/usr/bin/env bash
# Decide whether a Git ref may publish and deploy a staging release (ADR 0017).
# Prints key=value lines for $GITHUB_OUTPUT.
#   branch (any)              -> publish=false (checks only; never deploys staging)
#   tag stg.YYMMDD.N          -> publish when the date is valid, N >= 1, and the commit is
#                                reachable from origin/main (historical main commits allowed)
#   any other tag             -> refused
# Run inside a checkout that has origin/main (fetch-depth 0).
#
# Usage: staging-release-target.sh <branch|tag> <ref-name> <full-commit-sha>
set -euo pipefail

ref_type="${1:-}"
ref_name="${2:-}"
sha="${3:-}"

if [[ ! "${ref_type}" =~ ^(branch|tag)$ || -z "${ref_name}" || -z "${sha}" ]]; then
  echo "Usage: $0 <branch|tag> <ref-name> <full-commit-sha>" >&2
  exit 1
fi

if [[ ! "${sha}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "${sha} is not a full 40-character commit SHA" >&2
  exit 1
fi

if [[ "${ref_type}" == "branch" ]]; then
  echo "publish=false"
  exit 0
fi

if [[ ! "${ref_name}" =~ ^stg\.([0-9]{6})\.([1-9][0-9]*)$ ]]; then
  echo "${ref_name} is not a valid staging release tag (stg.YYMMDD.N, N >= 1)" >&2
  exit 1
fi

date_part="${BASH_REMATCH[1]}"
yy="${date_part:0:2}"
mm="${date_part:2:2}"
dd="${date_part:4:2}"
# Two-digit years map into 2000-2099 for calendar validation (portable; no GNU date).
if ! python3 -c "from datetime import date; date(2000 + int('${yy}'), int('${mm}'), int('${dd}'))" \
  >/dev/null 2>&1; then
  echo "${ref_name} date ${date_part} is not a valid calendar date" >&2
  exit 1
fi

if ! git merge-base --is-ancestor "${sha}" origin/main; then
  echo "Tag ${ref_name} (${sha}) is not reachable from origin/main" >&2
  exit 1
fi

cat <<EOF
publish=true
image_tag=${ref_name}
release=${ref_name}
revision=${sha}
EOF
