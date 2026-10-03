#!/usr/bin/env bash
# Per-boot services for rooted-core-api: Postgres, Redis, migrations, API.
set -euo pipefail

echo "rooted environment.json: cloud-agent-start"

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

postgres_version() {
  # Do not probe with `ls /etc/postgresql` in a pipeline. With pipefail, a
  # missing directory makes that assignment exit 2 before the error below.
  if [[ ! -d /etc/postgresql ]]; then
    return 0
  fi
  ls /etc/postgresql | sort -V | tail -1
}

start_postgres() {
  if command -v pg_isready >/dev/null 2>&1 && pg_isready -q; then
    return 0
  fi
  local ver pidfile pid
  ver="$(postgres_version)"
  if [[ -z "${ver}" ]]; then
    echo "PostgreSQL is not installed" >&2
    return 1
  fi
  pidfile="/var/lib/postgresql/${ver}/main/postmaster.pid"
  if [[ -f "${pidfile}" ]]; then
    pid="$(sudo head -n 1 "${pidfile}" || true)"
    if [[ -n "${pid}" ]] && ! sudo kill -0 "${pid}" 2>/dev/null; then
      sudo rm -f "${pidfile}"
    fi
  fi
  sudo pg_ctlcluster "${ver}" main start
}

start_redis() {
  if redis-cli ping 2>/dev/null | grep -q PONG; then
    return 0
  fi
  local pidfile="/run/redis/redis-server.pid" pid
  if [[ -f "${pidfile}" ]]; then
    pid="$(sudo head -n 1 "${pidfile}" || true)"
    if [[ -n "${pid}" ]] && ! sudo kill -0 "${pid}" 2>/dev/null; then
      sudo rm -f "${pidfile}"
    fi
  fi
  sudo service redis-server start
}

cd_repo
start_postgres
until pg_isready -q; do sleep 1; done

sudo -u postgres psql -v ON_ERROR_STOP=1 -c "ALTER USER postgres WITH PASSWORD 'postgres';"
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname = 'rooted-portal'" | grep -q 1; then
  sudo -u postgres psql -v ON_ERROR_STOP=1 -c 'CREATE DATABASE "rooted-portal";'
fi

# Schema defaults call uuidv7(). That function is built into PostgreSQL 18.
# Ubuntu 24.04 ships PostgreSQL 16, so install a compatible function there.
pg_version_num="$(sudo -u postgres psql -tAc 'SHOW server_version_num')"
if [[ "${pg_version_num}" -lt 180000 ]]; then
  sudo -u postgres psql -d "rooted-portal" -v ON_ERROR_STOP=1 <<'SQL'
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE OR REPLACE FUNCTION uuidv7() RETURNS uuid
LANGUAGE plpgsql
PARALLEL SAFE
VOLATILE
AS $$
DECLARE
  ts_ms bigint;
  uuid_bytes bytea;
BEGIN
  ts_ms := floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint;
  uuid_bytes := substring(int8send(ts_ms) FROM 3 FOR 6) || gen_random_bytes(10);
  uuid_bytes := set_byte(uuid_bytes, 6, (get_byte(uuid_bytes, 6) & 15) | 112);
  uuid_bytes := set_byte(uuid_bytes, 8, (get_byte(uuid_bytes, 8) & 63) | 128);
  RETURN encode(uuid_bytes, 'hex')::uuid;
END
$$;
SQL
fi

start_redis
until redis-cli ping 2>/dev/null | grep -q PONG; do sleep 1; done

if [[ ! -f .env ]]; then
  cp example.env .env
fi
# example.env leaves these blank. An empty SQL_ECHO is not a valid bool, and
# empty JWT material is loaded as "" rather than the code default.
sed -i \
  -e 's/^SQL_ECHO=$/SQL_ECHO=false/' \
  -e 's/^JWT_SECRET_KEY=$/JWT_SECRET_KEY=local-dev-only-not-a-secret/' \
  -e 's/^REFRESH_TOKEN_HASH_SALT=$/REFRESH_TOKEN_HASH_SALT=local-dev-salt/' \
  -e 's/^REFRESH_TOKEN_HASH_PEPPER=$/REFRESH_TOKEN_HASH_PEPPER=local-dev-pepper/' \
  .env

if curl -sf http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
  echo "API already listening on :8000"
  exit 0
fi

uv run alembic upgrade head
# init-locales upserts on (language_code, script_code, region_code). English
# uses NULL script/region, and Postgres does not treat those NULLs as equal,
# so a second run inserts the same primary key and fails. Skip when present.
if ! sudo -u postgres psql -d "rooted-portal" -tAc "SELECT 1 FROM public.system_locale WHERE id = '019dd0c8-69fa-7657-87bb-3b7255f5c5ae'" | grep -q 1; then
  uv run rooted-cli init-locales
fi
uv run rooted-cli seed-identity-providers
uv run rooted-cli seed-legal-documents
uv run rooted-cli seed-system-settings
uv run rooted-cli init-rbac

exec uv run uvicorn portal.main:app --host 0.0.0.0 --port 8000
