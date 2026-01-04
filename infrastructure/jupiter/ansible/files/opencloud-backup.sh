#!/bin/bash
# OpenCloud backup script for Scaleway Object Storage
# Runs every 4 hours via systemd timer
# Uses rclone sync for incremental backups

set -euo pipefail

# Load Scaleway credentials from secure file
if [ -f /root/.scaleway-credentials ]; then
    source /root/.scaleway-credentials
fi

BACKUP_DIRS="/etc/opencloud /var/lib/opencloud /var/lib/radicale /var/lib/vaultwarden/data"
REMOTE="scaleway:jupiter-backup"
LOG_FILE="/var/log/opencloud-backup.log"

# Function to log messages
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "Starting OpenCloud incremental backup"

# Sync each directory to remote storage
for dir in $BACKUP_DIRS; do
    if [ -d "$dir" ]; then
        # Extract directory name for remote path (e.g., /var/lib/opencloud -> var/lib/opencloud)
        remote_path="${dir#/}"
        log "Syncing $dir to $REMOTE/$remote_path"

        # Use rclone sync to mirror the directory (only transfer changes)
        rclone sync "$dir" "$REMOTE/$remote_path" \
            --progress \
            --transfers 4 \
            --checkers 8 \
            --stats-one-line \
            --log-level INFO \
            2>&1 | tee -a "$LOG_FILE"

        if [ ${PIPESTATUS[0]} -eq 0 ]; then
            log "Successfully synced $dir"
        else
            log "ERROR: Failed to sync $dir"
        fi
    else
        log "WARNING: Directory $dir does not exist, skipping..."
    fi
done

log "Backup completed successfully"
