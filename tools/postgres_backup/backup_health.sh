#!/bin/sh
set -eu

max_age="${BACKUP_MAX_AGE_SECONDS:-5400}"
case "$max_age" in *[!0-9]*|'') echo "BACKUP_MAX_AGE_SECONDS debe ser numérico" >&2; exit 2;; esac

latest="$(ls -1t /backups/*.dump 2>/dev/null | head -n 1 || true)"
[ -n "$latest" ] || { echo "Todavía no existe un respaldo válido" >&2; exit 1; }

mtime="$(stat -c %Y "$latest")"
now="$(date +%s)"
age=$((now - mtime))
[ "$age" -ge 0 ] && [ "$age" -le "$max_age" ] || {
  echo "El último respaldo tiene ${age}s; máximo permitido ${max_age}s" >&2
  exit 1
}

sha256sum -c "${latest}.sha256" >/dev/null
