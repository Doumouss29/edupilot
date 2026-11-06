#!/usr/bin/env bash
# EduPilot: local recovery snapshot for PostgreSQL and uploaded files.
# Run inside the EduPilot container as its unprivileged application user.
# For disaster recovery this MUST be replicated to encrypted offsite storage.
set -Eeuo pipefail
umask 077

if [[ "${DB_ENGINE:-}" != "postgresql" ]]; then
  echo "ERROR: expected DB_ENGINE=postgresql; refusing a partial backup" >&2
  exit 1
fi
for binary in pg_dump pg_restore tar sha256sum; do
  if ! command -v "$binary" >/dev/null 2>&1; then
    echo "ERROR: missing $binary in image; backup not attempted" >&2
    exit 1
  fi
done
if [[ ! -d /data/uploads ]]; then
  echo "ERROR: /data/uploads not mounted; refusing incomplete backup" >&2
  exit 1
fi

root=/data/backups
mkdir -p "$root"
chmod 700 "$root"
# Atomic lock works even when multiple cron invocations overlap.
lock="$root/.backup-lock"
if ! mkdir "$lock" 2>/dev/null; then
  echo "ERROR: backup already running or stale lock at $lock" >&2
  exit 1
fi
temporary=""
cleanup() {
  if [[ -n "$temporary" && -d "$temporary" ]]; then rm -rf -- "$temporary"; fi
  rmdir "$lock" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
temporary="$(mktemp -d "$root/.backup-${stamp}-XXXXXXXX")"
chmod 700 "$temporary"
schema="${PGSCHEMA:-edupilot}"
case "$schema" in
  edupilot|edupilot_recette) ;;
  *) echo "ERROR: unexpected PGSCHEMA, refusing partial backup" >&2; exit 1 ;;
esac
echo "Backing up PostgreSQL schema ${schema}, UTC ${stamp}"
pg_dump --format=custom --no-owner --no-acl --schema="$schema" --file="$temporary/postgresql.dump"
pg_restore --list "$temporary/postgresql.dump" >/dev/null
echo "Backing up uploaded files"
tar -C /data -czf "$temporary/uploads.tar.gz" uploads
tar -tzf "$temporary/uploads.tar.gz" >/dev/null
(
  cd "$temporary"
  sha256sum postgresql.dump uploads.tar.gz >SHA256SUMS
  sha256sum -c SHA256SUMS >/dev/null
)
printf 'timestamp_utc=%s\nschema=%s\n' "$stamp" "$schema" >"$temporary/MANIFEST.txt"
final="$root/edupilot-${stamp}"
if [[ -e "$final" ]]; then
  echo "ERROR: backup target already exists" >&2
  exit 1
fi
mv -- "$temporary" "$final"
temporary=""
# Keep the latest 7 verified local backup directories. Fail closed on partial runs.
mapfile -t existing < <(find "$root" -mindepth 1 -maxdepth 1 -type d -name 'edupilot-*' -printf '%f\n' | sort -r)
if (( ${#existing[@]} > 7 )); then
  for old in "${existing[@]:7}"; do
    [[ "$old" =~ ^edupilot-[0-9]{8}T[0-9]{6}Z$ ]] || continue
    rm -rf -- "$root/$old"
  done
fi
echo "VERIFIED_BACKUP=$final"
echo "NOTICE: Local copy only; encrypted offsite replication and restore test still required."
