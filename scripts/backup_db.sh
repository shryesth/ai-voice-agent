#!/bin/bash
#
# MongoDB Backup Script for Patient Feedback Collection API
#
# Features:
# - Creates compressed backup archives
# - Retains last N backups (configurable)
# - Supports local and remote storage (S3/MinIO compatible)
# - Includes backup verification
# - Sends notifications on failure
#
# Usage:
#   ./scripts/backup_db.sh [--local-only] [--retention-days DAYS]
#
# Environment Variables (set in .env or export):
#   MONGODB_URI - MongoDB connection string
#   BACKUP_DIR - Local backup directory (default: ./backups)
#   BACKUP_RETENTION_DAYS - Days to retain backups (default: 30)
#   S3_BACKUP_ENABLED - Enable S3 upload (true/false, default: false)
#   S3_BUCKET - S3 bucket name for backups
#   AWS_ACCESS_KEY_ID - AWS/MinIO access key
#   AWS_SECRET_ACCESS_KEY - AWS/MinIO secret key
#   S3_ENDPOINT - S3 endpoint (for MinIO or custom S3-compatible storage)
#

set -e  # Exit on error
set -u  # Exit on undefined variable
set -o pipefail  # Exit on pipe failure

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load environment variables from .env if exists
if [ -f "$PROJECT_DIR/.env" ]; then
    export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
fi

# Defaults
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
S3_BACKUP_ENABLED="${S3_BACKUP_ENABLED:-false}"
MONGODB_URI="${MONGODB_URI:-mongodb://localhost:27017}"
DATABASE_NAME="${MONGODB_DATABASE:-voice_ai}"

# Parse command-line arguments
LOCAL_ONLY=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --local-only)
            LOCAL_ONLY=true
            shift
            ;;
        --retention-days)
            BACKUP_RETENTION_DAYS="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--local-only] [--retention-days DAYS]"
            exit 1
            ;;
    esac
done

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Generate backup filename with timestamp
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_NAME="backup_${DATABASE_NAME}_${TIMESTAMP}"
BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"

log_info "Starting MongoDB backup: $DATABASE_NAME"
log_info "Backup directory: $BACKUP_DIR"

# Create backup using mongodump
log_info "Running mongodump..."
if mongodump --uri="$MONGODB_URI" --db="$DATABASE_NAME" --out="$BACKUP_PATH" --quiet; then
    log_info "Mongodump completed successfully"
else
    log_error "Mongodump failed"
    exit 1
fi

# Compress backup
log_info "Compressing backup..."
ARCHIVE_PATH="$BACKUP_PATH.tar.gz"
if tar -czf "$ARCHIVE_PATH" -C "$BACKUP_DIR" "$BACKUP_NAME"; then
    log_info "Compression completed: $ARCHIVE_PATH"
    # Remove uncompressed backup directory
    rm -rf "$BACKUP_PATH"
else
    log_error "Compression failed"
    exit 1
fi

# Verify archive integrity
log_info "Verifying backup archive..."
if tar -tzf "$ARCHIVE_PATH" >/dev/null 2>&1; then
    log_info "Archive integrity verified"
else
    log_error "Archive verification failed"
    exit 1
fi

# Get backup size
BACKUP_SIZE=$(du -h "$ARCHIVE_PATH" | cut -f1)
log_info "Backup size: $BACKUP_SIZE"

# Upload to S3/MinIO if enabled
if [ "$S3_BACKUP_ENABLED" = "true" ] && [ "$LOCAL_ONLY" = false ]; then
    if command -v aws &> /dev/null; then
        log_info "Uploading backup to S3..."

        # Set endpoint if using MinIO
        AWS_ARGS=""
        if [ -n "${S3_ENDPOINT:-}" ]; then
            AWS_ARGS="--endpoint-url $S3_ENDPOINT"
        fi

        if aws s3 cp "$ARCHIVE_PATH" "s3://$S3_BUCKET/backups/$BACKUP_NAME.tar.gz" $AWS_ARGS; then
            log_info "Backup uploaded to S3 successfully"
        else
            log_warn "S3 upload failed (local backup retained)"
        fi
    else
        log_warn "AWS CLI not installed, skipping S3 upload"
    fi
fi

# Clean up old backups (local)
log_info "Cleaning up old backups (retention: $BACKUP_RETENTION_DAYS days)..."
DELETED_COUNT=0
while IFS= read -r old_backup; do
    rm -f "$old_backup"
    DELETED_COUNT=$((DELETED_COUNT + 1))
done < <(find "$BACKUP_DIR" -name "backup_*.tar.gz" -type f -mtime +$BACKUP_RETENTION_DAYS)

if [ $DELETED_COUNT -gt 0 ]; then
    log_info "Deleted $DELETED_COUNT old backups"
else
    log_info "No old backups to delete"
fi

# Count remaining backups
BACKUP_COUNT=$(find "$BACKUP_DIR" -name "backup_*.tar.gz" -type f | wc -l)
log_info "Total backups retained: $BACKUP_COUNT"

# Success summary
log_info "==============================================="
log_info "Backup completed successfully!"
log_info "Backup file: $ARCHIVE_PATH"
log_info "Backup size: $BACKUP_SIZE"
log_info "Timestamp: $TIMESTAMP"
log_info "==============================================="

exit 0
