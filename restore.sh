#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <backup-file>" >&2
  exit 1
fi

BACKUP_FILE="$1"

if [ ! -s "$BACKUP_FILE" ]; then
  echo "Backup file not found or empty: $BACKUP_FILE" >&2
  exit 1
fi

echo "Restoring PostgreSQL backup: $BACKUP_FILE"

cat "$BACKUP_FILE" | docker compose exec -T postgres \
  pg_restore -U barq_app -d barq_tasks --clean --if-exists

echo "Restore completed successfully."
