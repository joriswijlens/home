#!/bin/bash
# Provision the `paperclip` database and `paperclip` role on the shared Postgres
# instance. Privileges are scoped to the paperclip database only.
#
# This script runs once on first container start (when /var/lib/postgresql/data
# is empty). To re-run on an existing instance, exec it manually.
#
# Convention: each future service that needs an RDB on Jupiter creates its own
# init script here (e.g. 02-foo.sh) provisioning a DB + role with rights scoped
# to that DB only. Do NOT grant cross-database privileges.

set -euo pipefail

if [ -z "${PAPERCLIP_DB_PASSWORD:-}" ]; then
    echo "ERROR: PAPERCLIP_DB_PASSWORD is not set; refusing to create role with empty password" >&2
    exit 1
fi

psql --variable=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE paperclip WITH LOGIN PASSWORD '${PAPERCLIP_DB_PASSWORD}';
    CREATE DATABASE paperclip OWNER paperclip;
    REVOKE ALL ON DATABASE paperclip FROM PUBLIC;
    GRANT CONNECT, TEMP ON DATABASE paperclip TO paperclip;
EOSQL

psql --variable=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname paperclip <<-EOSQL
    GRANT ALL ON SCHEMA public TO paperclip;
EOSQL
