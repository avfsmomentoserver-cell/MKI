#!/usr/bin/env bash
# backup.sh — production backup of the `mkc` Postgres database.
#
#   - pg_dump custom format (-Fc) -> ${MKC_BACKUP_DIR}/mkc-YYYYmmdd-HHMMSS.dump
#     (default dir: /home/admin/MKI/backups)
#   - Credentials: PG* / PGPASSWORD environment when set; otherwise
#     DATABASE_URL is parsed out of the repo .env. The URL (and therefore
#     the password) is never printed: pg_dump stdout/stderr go to a scratch
#     file, and if the dump fails, the error excerpt is logged with the
#     password redacted.
#   - Retention: the newest 30 dumps are kept; each pruned file is logged.
#   - Timestamped log: ${MKC_BACKUP_DIR}/backup.log (secret-free).
#   - Fails loudly: set -euo pipefail, non-zero exit on any failure, and a
#     failed dump never leaves a partial .dump behind (temp file + rename).
set -euo pipefail

REPO_ROOT="/home/admin/MKI"
ENV_FILE="${REPO_ROOT}/.env"
BACKUP_DIR="${MKC_BACKUP_DIR:-${REPO_ROOT}/backups}"
DB_NAME="mkc"
KEEP_COUNT=30

mkdir -p "${BACKUP_DIR}"
LOG_FILE="${BACKUP_DIR}/backup.log"
# Dumps and the log can outlive the session; keep them owner-private.
chmod 600 "${LOG_FILE}" 2>/dev/null || true

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $*" | tee -a "${LOG_FILE}"; }
die() { log "ERROR: $*"; exit 1; }

# Redact a secret from text before logging it (defense in depth).
redact() { # redact <text> <secret>
  local text="$1" secret="$2" esc
  if [[ -z "${secret}" ]]; then
    printf '%s' "${text}"
    return 0
  fi
  esc="$(printf '%s' "${secret}" | sed -e 's/[][\.*^$/]/\\&/g')"
  printf '%s' "${text}" | sed "s/${esc}/****/g"
}

# --- credentials (resolved, never echoed) -----------------------------------
CRED_SOURCE="PG* environment"
if [[ -z "${PGHOST:-}${PGPORT:-}${PGUSER:-}${PGPASSWORD:-}" ]]; then
  [[ -f "${ENV_FILE}" ]] || die ".env not found: ${ENV_FILE}"
  url_line="$(grep -E '^DATABASE_URL=' "${ENV_FILE}" | head -n1)"
  [[ -n "${url_line}" ]] || die "DATABASE_URL line not found in ${ENV_FILE}"
  url_value="${url_line#*=}"
  CRED_SOURCE="parsed from .env DATABASE_URL"

  # shape: scheme://[user[:password]@]host[:port]/dbname
  rest="${url_value#*://}"
  [[ "${rest}" != "${url_value}" ]] || die "DATABASE_URL: expected a URL with a scheme"
  authority="${rest%%/*}"
  PG_DB="${rest#*/}"
  [[ "${PG_DB}" != "${rest}" && -n "${PG_DB}" ]] || die "DATABASE_URL: missing database name"

  userpass=""
  if [[ "${authority}" == *@* ]]; then
    userpass="${authority%%@*}"
    hostport="${authority#*@}"
  else
    hostport="${authority}"
  fi
  if [[ -n "${userpass}" ]]; then
    PG_USER="${userpass%%:*}"
    if [[ "${userpass}" == *:*** ]]; then
      PG_PASS="${userpass#*:}"
    else
      PG_PASS=""
    fi
  else
    PG_USER=""
    PG_PASS=""
  fi
  PG_HOST="${hostport%%:*}"
  PG_PORT="${hostport#*:}"
  [[ "${PG_PORT}" == "${PG_HOST}" ]] && PG_PORT="5432"
  [[ -n "${PG_HOST}" ]] || die "DATABASE_URL: missing host"
  [[ -n "${PG_PASS}" ]] || die "DATABASE_URL: no embedded password and PGPASSWORD unset"
else
  PG_HOST="${PGHOST:-localhost}"
  PG_PORT="${PGPORT:-5432}"
  PG_USER="${PGUSER:-}"
  PG_PASS="${PGPASSWORD}"
  [[ -n "${PG_PASS}" ]] || die "PG* environment set but PGPASSWORD is empty"
fi

# --- dump --------------------------------------------------------------------
TS="$(date +%Y%m%d-%H%M%S)"
DUMP_FILE="${BACKUP_DIR}/mkc-${TS}.dump"
TMP_FILE="${DUMP_FILE}.tmp"
SCRATCH="$(mktemp "${BACKUP_DIR}/.pgdump.XXXXXX")"
chmod 600 "${SCRATCH}"

log "backup start: db=${DB_NAME} dir=${BACKUP_DIR} creds=${CRED_SOURCE}"
trap 'log "ERROR: backup failed at line ${LINENO} (exit ${?})"' ERR
trap 'rm -f "${SCRATCH}"' EXIT

PG_DUMP_ARGS=(--host="${PG_HOST}" --port="${PG_PORT}" --format=custom
              --dbname="${DB_NAME}" --file="${TMP_FILE}")
[[ -n "${PG_USER}" ]] && PG_DUMP_ARGS+=(--username="${PG_USER}")

set +e
PGPASSWORD="${PG_PASS}" pg_dump "${PG_DUMP_ARGS[@]}" >"${SCRATCH}" 2>&1
DUMP_STATUS=$?
set -e

if [[ "${DUMP_STATUS}" -ne 0 ]]; then
  rm -f "${TMP_FILE}"
  EXCERPT="$(redact "$(tail -n 5 "${SCRATCH}")" "${PG_PASS}")"
  log "ERROR: pg_dump failed (exit ${DUMP_STATUS}); output excerpt (redacted): ${EXCERPT}"
  exit "${DUMP_STATUS}"
fi

mv -f "${TMP_FILE}" "${DUMP_FILE}"
chmod 600 "${DUMP_FILE}"
DUMP_SIZE="$(du -h "${DUMP_FILE}" | cut -f1)"
log "dump ok: file=${DUMP_FILE} size=${DUMP_SIZE} (pg_dump custom format)"

# --- retention: keep the newest ${KEEP_COUNT} dumps; log every prune ----------
PRUNED=0
while IFS= read -r OLD; do
  [[ -n "${OLD}" ]] || continue
  rm -f "${OLD}"
  log "retention: pruned ${OLD##*/}"
  PRUNED=$((PRUNED + 1))
done < <(find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'mkc-*.dump' -printf '%T@\t%p\n' \
  | sort -rn | tail -n +$((KEEP_COUNT + 1)) | cut -f2-)

log "backup complete: file=${DUMP_FILE} pruned=${PRUNED}"
