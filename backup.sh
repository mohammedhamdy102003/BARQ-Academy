#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="${BACKUP_DIR}/barq_tasks_${TIMESTAMP}.dump"

mkdir -p "$BACKUP_DIR"

echo "Creating PostgreSQL backup: $BACKUP_FILE"

docker compose exec -T postgres \
  pg_dump -U barq_app -d barq_tasks -Fc \
  > "$BACKUP_FILE"

test -s "$BACKUP_FILE"

echo "Backup completed successfully."
echo "Backup file: $BACKUP_FILE"
ls -lh "$BACKUP_FILE"
