#!/bin/bash
# Dump every database in the shared Jupiter Postgres instance to a compressed
# pg_dump artifact under /var/lib/postgres-dumps/. Runs every 4 hours via
# systemd timer; the existing rclone job (opencloud-backup.timer) ships these
# dumps to Scaleway.
#
# We dump from inside the running container with `docker exec` so the host
# does not need postgresql-client installed and the dump uses the same
# Postgres version that wrote the data files.
#
# We deliberately do NOT rclone the live postgres-data Docker volume: copying
# the on-disk files while Postgres has writes in flight produces a torn,
# unrestorable snapshot.

set -euo pipefail

DUMP_DIR="/var/lib/postgres-dumps"
CONTAINER="postgres"
RETENTION_COUNT=12  # keep last 12 dumps per database (~2 days at 4h cadence)
LOG_FILE="/var/log/postgres-dump.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

mkdir -p "$DUMP_DIR"
chmod 700 "$DUMP_DIR"

if ! docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -q true; then
    log "ERROR: container '$CONTAINER' is not running, skipping dump"
    exit 1
fi

log "Starting Postgres dump"

# List all non-template databases.
mapfile -t DATABASES < <(docker exec "$CONTAINER" psql -U postgres -At -c \
    "SELECT datname FROM pg_database WHERE datistemplate = false AND datname <> 'postgres';")

if [ ${#DATABASES[@]} -eq 0 ]; then
    log "No application databases found (only postgres/templates); nothing to dump"
fi

TIMESTAMP=$(date -u '+%Y%m%dT%H%M%SZ')
FAILED=0

for db in "${DATABASES[@]}"; do
    out="${DUMP_DIR}/${db}-${TIMESTAMP}.dump"
    tmp="${out}.partial"
    log "Dumping database '$db' -> $out"

    # -Fc = custom (compressed) format, restorable with pg_restore.
    if docker exec "$CONTAINER" pg_dump -U postgres -Fc -d "$db" > "$tmp"; then
        mv "$tmp" "$out"
        chmod 600 "$out"
        log "OK: $(stat -c %s "$out") bytes written"
    else
        log "ERROR: pg_dump failed for '$db'"
        rm -f "$tmp"
        FAILED=1
        continue
    fi

    # Prune older dumps for this database, keep the most recent RETENTION_COUNT.
    ls -1t "${DUMP_DIR}/${db}-"*.dump 2>/dev/null | tail -n +$((RETENTION_COUNT + 1)) | \
        while read -r old; do
            log "Pruning old dump: $old"
            rm -f "$old"
        done
done

if [ "$FAILED" -ne 0 ]; then
    log "Postgres dump finished with errors"
    exit 1
fi

log "Postgres dump completed successfully"
