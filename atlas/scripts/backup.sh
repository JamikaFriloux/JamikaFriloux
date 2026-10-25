#!/usr/bin/env bash
# Daily PostgreSQL backup for the Docker Compose deployment.
# Usage: scripts/backup.sh [output_dir]   (default ./backups)
# Store backups off-host and encrypted (e.g. restic, age, or a cloud bucket with SSE).
set -euo pipefail
out="${1:-./backups}"
mkdir -p "$out"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
docker compose exec -T postgres pg_dump -U atlas -d atlas --format=custom \
  | gzip > "$out/atlas-$stamp.dump.gz"
echo "wrote $out/atlas-$stamp.dump.gz"
# Restore:
#   gunzip -c backups/atlas-<stamp>.dump.gz | docker compose exec -T postgres \
#     pg_restore -U atlas -d atlas --clean --if-exists
