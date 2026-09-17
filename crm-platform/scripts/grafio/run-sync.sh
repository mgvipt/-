#!/usr/bin/env bash
set -euo pipefail
umask 077
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR=/var/lib/wallcov-grafio
CONTAINER=crm-platform-web-1
case "${1:---dry-run}" in
  --dry-run)
    printf '%s\n' 'DRY RUN: no files, crawl, container or CRM changes.' \
      'Require private bind /var/lib/wallcov-grafio:/var/lib/wallcov-grafio on crm-platform-web-1.' \
      'flock -> crawl 223 public pages -> immutable unique snapshot -> docker cp -> importer read-only validation -> backup + --apply --all --push.' \
      'Previous snapshot/prices survive any crawl failure; import failures require review of the retained backup.'
    exit 0 ;;
  --apply) ;;
  *) printf '%s\n' 'Usage: run-sync.sh [--dry-run|--apply]' >&2; exit 2 ;;
esac
mkdir -p "$STATE_DIR/snapshots" "$STATE_DIR/backups" "$STATE_DIR/incoming"
exec 9>"$STATE_DIR/sync.lock"
flock -n 9 || { printf '%s\n' 'Another Grafio sync is active; skipped.'; exit 0; }
# Fail closed: a container-layer or public media backup is not acceptable.
docker inspect -f '{{range .Mounts}}{{if and (eq .Source "/var/lib/wallcov-grafio") (eq .Destination "/var/lib/wallcov-grafio") .RW}}private-bind-ok{{end}}{{end}}' "$CONTAINER" | grep -qx private-bind-ok
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
SNAPSHOT="$STATE_DIR/snapshots/$RUN_ID.json"
INPUT="$STATE_DIR/inventory.json"
BACKUP="$STATE_DIR/backups/$RUN_ID-before.json"
CONTAINER_SNAPSHOT="$STATE_DIR/incoming/$RUN_ID.json"
[[ -f "$INPUT" && ! -e "$SNAPSHOT" && ! -e "$BACKUP" ]]
python3 "$SCRIPT_DIR/sync.py" --inventory "$INPUT" --output "$SNAPSHOT"
# sync.py writes only a complete snapshot, by atomic rename.
chmod 0400 "$SNAPSHOT"
docker cp "$SNAPSHOT" "$CONTAINER:$CONTAINER_SNAPSHOT"
docker exec -w /app "$CONTAINER" python manage.py import_grafio_catalog "$CONTAINER_SNAPSHOT"
docker exec -e DRY_RUN=0 -w /app "$CONTAINER" python manage.py import_grafio_catalog "$CONTAINER_SNAPSHOT" --apply --all --backup "$BACKUP" --push
printf '%s\n' "Grafio sync completed: $RUN_ID; snapshot and pre-import backup retained."
