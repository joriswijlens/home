#!/bin/bash
# Venus AI node backup script for Scaleway Object Storage
# Runs every 6 hours via systemd timer
# Uses rclone sync for incremental backups

set -euo pipefail

# Load Scaleway credentials from secure file
if [ -f /root/.scaleway-credentials ]; then
    source /root/.scaleway-credentials
fi

BACKUP_DIRS="/opt/smartworkx/volumes"
REMOTE="scaleway:com-smartworkx-venus-backup"
LOG_FILE="/var/log/venus-backup.log"

# Function to log messages
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "Starting Venus AI node incremental backup"

# Sync volumes directory to remote storage
if [ -d "$BACKUP_DIRS" ]; then
    log "Syncing $BACKUP_DIRS to $REMOTE/opt/smartworkx/volumes"

    # Use rclone sync to mirror the directory (only transfer changes)
    rclone sync "$BACKUP_DIRS" "$REMOTE/opt/smartworkx/volumes" \
        --progress \
        --transfers 4 \
        --checkers 8 \
        --stats-one-line \
        --log-level INFO \
        2>&1 | tee -a "$LOG_FILE"

    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        log "Successfully synced $BACKUP_DIRS"
    else
        log "ERROR: Failed to sync $BACKUP_DIRS"
        exit 1
    fi
else
    log "ERROR: Directory $BACKUP_DIRS does not exist"
    exit 1
fi

log "Backup completed successfully"
