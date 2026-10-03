#!/usr/bin/env bash
# Idempotent Cloud Agent install for rooted-core-api.
set -euo pipefail

echo "rooted environment.json: cloud-agent-install"

export DEBIAN_FRONTEND=noninteractive

sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  git \
  build-essential \
  pkg-config \
  libpq-dev \
  postgresql \
  postgresql-contrib \
  redis-server

UV_VERSION=0.12.22
UV_SHA256=b9980552309f09c15172b8be828555e375097f16deb459795ce7bfd200380f0b
if ! command -v uv >/dev/null 2>&1 || [[ "$(uv --version 2>/dev/null || true)" != "uv ${UV_VERSION}"* ]]; then
  tmp="$(mktemp -d)"
  curl -fsSL -o "${tmp}/uv.tar.gz" \
    "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz"
  echo "${UV_SHA256}  ${tmp}/uv.tar.gz" | sha256sum -c -
  tar -xzf "${tmp}/uv.tar.gz" -C "${tmp}"
  sudo install -m 0755 "${tmp}/uv-x86_64-unknown-linux-gnu/uv" /usr/local/bin/uv
  sudo install -m 0755 "${tmp}/uv-x86_64-unknown-linux-gnu/uvx" /usr/local/bin/uvx
  rm -rf "${tmp}"
fi

cd_repo() {
  if [[ -f pyproject.toml && -d portal ]]; then
    return 0
  fi
  local candidate
  for candidate in /workspace /workspace/rooted-core-api /agent/repos/rooted-core-api; do
    if [[ -f "${candidate}/pyproject.toml" && -d "${candidate}/portal" ]]; then
      cd "${candidate}"
      return 0
    fi
  done
  echo "rooted-core-api checkout not found from ${PWD}" >&2
  return 1
}

cd_repo
uv python install 3.14
uv sync --frozen
