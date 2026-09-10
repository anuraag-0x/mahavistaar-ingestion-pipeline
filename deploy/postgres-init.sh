#!/bin/sh
set -eu

: "${KEYCLOAK_DB:?KEYCLOAK_DB must be set}"
: "${KEYCLOAK_DB_USER:?KEYCLOAK_DB_USER must be set}"
: "${KEYCLOAK_DB_PASSWORD:?KEYCLOAK_DB_PASSWORD must be set}"

escaped_user=$(printf '%s' "$KEYCLOAK_DB_USER" | sed "s/'/''/g")
escaped_password=$(printf '%s' "$KEYCLOAK_DB_PASSWORD" | sed "s/'/''/g")
escaped_db=$(printf '%s' "$KEYCLOAK_DB" | sed "s/'/''/g")

if [ "$KEYCLOAK_DB_USER" != "$POSTGRES_USER" ]; then
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v kc_user="$escaped_user" -v kc_password="$escaped_password" \
    -c "CREATE ROLE \"$escaped_user\" LOGIN PASSWORD '$escaped_password';" 2>/dev/null || true
else
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -c "ALTER ROLE \"$escaped_user\" WITH PASSWORD '$escaped_password';"
fi

if ! psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname = '$escaped_db'" | grep -q 1; then
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
    -c "CREATE DATABASE \"$escaped_db\" OWNER \"$escaped_user\";"
fi
