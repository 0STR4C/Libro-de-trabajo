#!/bin/sh
set -eu
umask 077

interval="${BACKUP_INTERVAL_SECONDS:-3600}"
case "$interval" in *[!0-9]*|'') echo "BACKUP_INTERVAL_SECONDS debe ser numérico" >&2; exit 2;; esac
if [ "$interval" -lt 300 ]; then echo "El intervalo mínimo es de 300 segundos" >&2; exit 2; fi

mkdir -p /backups

while true; do
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  final="/backups/centro_operativo_${stamp}.dump"
  partial="${final}.partial"
  trap 'rm -f "$partial"' EXIT INT TERM
  PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --file="$partial"
  pg_restore --list "$partial" >/dev/null
  mv "$partial" "$final"
  sha256sum "$final" > "${final}.sha256"
  trap - EXIT INT TERM
  echo "Respaldo verificado: $final"
  [ "${BACKUP_RUN_ONCE:-0}" = "1" ] && exit 0
  sleep "$interval"
done
