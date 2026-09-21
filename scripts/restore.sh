#!/usr/bin/env bash
# restore.sh — restore-validate an MKC database dump.
#
#   Usage: scripts/restore.sh <dump-file>
#
# Project rule: a backup that has never been restored is not considered
# validated. This script proves a dump is restorable by restoring it into a
# throwaway database and reconciling it against the live `mkc` database:
#
#   1. alembic_version in the restored DB equals the live DB's head.
#   2. Row counts for all 12 content tables match the live DB.
#   3. 3 random knowledge_objects rows (by id) have a non-empty JSONB
#      `provenance` with keys source_type / source_location / extraction_method.
#   4. If the live DB has decisions, one full decision row exists in the
#      restored DB with an identical key.
#
# The throwaway database `mkc_restore_verify` is created if absent and dropped
# at the end — including on failure (trap). Exit 0 only if every check passes.
#
# Privilege model: pg_restore runs as the `postgres` superuser (via sudo, the
# operator on this host has passwordless sudo) because the dump embeds
# extension DDL only a superuser can execute; read checks then run as the
# app role `mkc`, so verification exercises a realistic read path.

set -euo pipefail

REPO_ROOT="/home/admin/MKI"
ENV_FILE="${REPO_ROOT}/.env"
SOURCE_DB="mkc"
VERIFY_DB="mkc_restore_verify"
TABLES=(sources documents knowledge_objects entities entity_relations research_items
        decisions experiments insights contradictions audit_log reports)

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $*"; }
die() { log "ERROR: $*" >&2; exit 1; }

DUMP_FILE="${1:-}"
[[ -n "${DUMP_FILE}" ]] || die "usage: $0 <dump-file>"
DUMP_FILE="$(readlink -f "${DUMP_FILE}")" || die "cannot resolve path: ${DUMP_FILE}"
[[ -f "${DUMP_FILE}" ]] || die "dump file not found: ${DUMP_FILE}"

# --- credentials (resolved, never echoed) ------------------------------------
# Same resolution as backup.sh: PG* env first, else .env DATABASE_URL.
if [[ -z "${PGHOST:-}${PGPORT:-}${PGUSER:-}${PGPASSWORD:-}" ]]; then
  [[ -f "${ENV_FILE}" ]] || die ".env not found: ${ENV_FILE}"
  url_line="$(grep -E '^DATABASE_URL=' "${ENV_FILE}" | head -n1)"
  [[ -n "${url_line}" ]] || die "DATABASE_URL line not found in ${ENV_FILE}"
  url_value="${url_line#*=}"
  rest="${url_value#*://}"
  authority="${rest%%/*}"
  if [[ "${authority}" == *@* ]]; then
    userpass="${authority%%@*}"
    hostport="${authority#*@}"
  else
    hostport="${authority}"
  fi
  PG_USER="${userpass%%:*}"
  if [[ "${userpass}" == *:*** ]]; then
    PG_PASS="${userpass#*:}"
  else
    PG_PASS=""
  fi
  PG_HOST="${hostport%%:*}"
  PG_PORT="${hostport#*:}"
  [[ "${PG_PORT}" == "${PG_HOST}" ]] && PG_PORT="5432"
else
  PG_HOST="${PGHOST:-localhost}"
  PG_PORT="${PGPORT:-5432}"
  PG_USER="${PGUSER:-mkc}"
  PG_PASS="${PGPASSWORD}"
fi
[[ -n "${PG_PASS}" ]] || die "no usable password (PGPASSWORD or .env DATABASE_URL)"

PG_CONN=(-h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}")
psql_app() { PGPASSWORD="${PG_PASS}" psql -qAt "${PG_CONN[@]}" -d "${SOURCE_DB}" "${@}"; }
psql_verify() { PGPASSWORD="${PG_PASS}" psql -qAt "${PG_CONN[@]}" -d "${VERIFY_DB}" "${@}"; }
psql_super() { sudo -u postgres psql -qAt -d postgres "${@}"; }

# --- throwaway DB lifecycle (dropped even on failure) -------------------------
DUMP_COPY="$(mktemp /tmp/mkc-restore-XXXXXX.dump)"
cleanup_files() { rm -f "${DUMP_COPY}"; }
drop_verify_db() {
  if psql_super -c "DROP DATABASE IF EXISTS ${VERIFY_DB};" >/dev/null 2>&1; then
    log "dropped throwaway database ${VERIFY_DB}"
  else
    log "WARNING: could not drop ${VERIFY_DB} — manual cleanup required"
  fi
}
trap 'cleanup_files; drop_verify_db' EXIT

log "restore-validate start: dump=${DUMP_FILE} verify_db=${VERIFY_DB}"
drop_verify_db
psql_super -c "CREATE DATABASE ${VERIFY_DB};" >/dev/null
log "created throwaway database ${VERIFY_DB}"

# The repo's backups dir is 700 admin:admin; the postgres system user cannot
# read it, so restore from a world-readable copy that is removed on exit.
cp "${DUMP_FILE}" "${DUMP_COPY}"
chmod 644 "${DUMP_COPY}"

# --- restore ------------------------------------------------------------------
set +e
sudo -u postgres pg_restore --exit-on-error --dbname="${VERIFY_DB}" "${DUMP_COPY}" >/tmp/mkc-pgrestore.out 2>&1
RESTORE_STATUS=$?
set -e
if [[ "${RESTORE_STATUS}" -ne 0 ]]; then
  log "ERROR: pg_restore failed (exit ${RESTORE_STATUS}); last lines:"
  tail -n 10 /tmp/mkc-pgrestore.out >&2
  exit "${RESTORE_STATUS}"
fi
rm -f /tmp/mkc-pgrestore.out
log "pg_restore ok"

# Realistic read path for the verification queries: app role only.
psql_super -d "${VERIFY_DB}" -c "GRANT ALL ON ALL TABLES IN SCHEMA public TO ${PG_USER};" >/dev/null
psql_super -d "${VERIFY_DB}" -c "GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO ${PG_USER};" >/dev/null

# --- results buffer -------------------------------------------------------------
PASS=0
FAIL=0
RESULTS=""

record() { # record <check> <status> <detail>
  local check="$1" status="$2" detail="$3"
  printf '  %-58s %-5s %s\n' "${check}" "${status}" "${detail}"
  RESULTS="${RESULTS}${check}|${status}|${detail}"$'\n'
  if [[ "${status}" == "PASS" ]]; then PASS=$((PASS + 1)); else FAIL=$((FAIL + 1)); fi
}

echo
echo "== Check 1: alembic head =="
SRC_HEAD="$(psql_app -c "SELECT version_num FROM alembic_version;")"
VRF_HEAD="$(psql_verify -c "SELECT version_num FROM alembic_version;")"
if [[ -n "${SRC_HEAD}" && "${SRC_HEAD}" == "${VRF_HEAD}" ]]; then
  record "alembic head matches live (${SRC_HEAD})" "PASS" "restored=${VRF_HEAD}"
else
  record "alembic head matches live" "FAIL" "live=${SRC_HEAD:-<none>} restored=${VRF_HEAD:-<none>}"
fi

echo
echo "== Check 2: row counts (${#TABLES[@]} tables) =="
for t in "${TABLES[@]}"; do
  src_n="$(psql_app -c "SELECT count(*) FROM public.${t};")"
  vrf_n="$(psql_verify -c "SELECT count(*) FROM public.${t};")"
  if [[ "${src_n}" == "${vrf_n}" ]]; then
    record "rows ${t}" "PASS" "live=${src_n} restored=${vrf_n}"
  else
    record "rows ${t}" "FAIL" "live=${src_n} restored=${vrf_n}"
  fi
done

echo
echo "== Check 3: provenance of 3 random knowledge_objects =="
KO_COUNT="$(psql_app -c "SELECT count(*) FROM knowledge_objects;")"
if [[ "${KO_COUNT}" == "0" ]]; then
  record "provenance sample (no knowledge_objects rows)" "PASS" "skipped: 0 rows in live DB"
else
  # 3 random ids from the live DB, quoted for the IN (...) list.
  SAMPLE_IDS="$(psql_app -c "SELECT id FROM knowledge_objects ORDER BY random() LIMIT 3;" | sed "s/^/'/; s/\$/'/" | paste -sd, -)"
  # One query on the restored DB, keyed by those ids.
  VRF_PROV="$(psql_verify -c "
SELECT id || '|' || jsonb_typeof(provenance) || '|' ||
  CASE WHEN provenance ? 'source_type' THEN '1' ELSE '0' END || '|' ||
  CASE WHEN provenance ? 'source_location' THEN '1' ELSE '0' END || '|' ||
  CASE WHEN provenance ? 'extraction_method' THEN '1' ELSE '0' END
FROM knowledge_objects
WHERE id IN (${SAMPLE_IDS});" )"
  PROV_OK=1
  PROV_DETAIL=""
  ROWS_SEEN=0
  while IFS= read -r row; do
    [[ -n "${row}" ]] || continue
    ROWS_SEEN=$((ROWS_SEEN + 1))
    id="${row%%|*}"; rest="${row#*|}"
    type="${rest%%|*}"; rest="${rest#*|}"
    k1="${rest%%|*}"; rest="${rest#*|}"
    k2="${rest%%|*}"; k3="${rest#*|}"
    if [[ "${type}" == "object" && "${k1}" == "1" && "${k2}" == "1" && "${k3}" == "1" ]]; then
      PROV_DETAIL="${PROV_DETAIL}${id:0:8}..ok "
    else
      PROV_OK=0
      PROV_DETAIL="${PROV_DETAIL}${id:0:8}..BAD(type=${type},st=${k1},sl=${k2},em=${k3}) "
    fi
  done <<< "${VRF_PROV}"
  if [[ "${ROWS_SEEN}" -lt 3 ]]; then
    PROV_OK=0
    PROV_DETAIL="restored DB returned ${ROWS_SEEN}/3 sampled rows. ${PROV_DETAIL}"
  fi
  if [[ "${PROV_OK}" -eq 1 ]]; then
    record "provenance keys on 3 random knowledge_objects" "PASS" "${PROV_DETAIL}"
  else
    record "provenance keys on 3 random knowledge_objects" "FAIL" "${PROV_DETAIL}"
  fi
fi

echo
echo "== Check 4: sample decision row =="
DEC_ID="$(psql_app -c "SELECT id FROM decisions LIMIT 1;")"
if [[ -z "${DEC_ID}" ]]; then
  record "sample decision row" "PASS" "skipped: no rows in live decisions table"
else
  DEC_PRESENT="$(psql_verify -c "SELECT count(*) FROM decisions WHERE id = '${DEC_ID}';")"
  if [[ "${DEC_PRESENT}" == "1" ]]; then
    record "sample decision row present (id ${DEC_ID:0:8}..)" "PASS" "full row exists in restored DB"
  else
    record "sample decision row present" "FAIL" "id ${DEC_ID} not found in restored DB"
  fi
fi

# --- summary table ---------------------------------------------------------------
echo
echo "============================================================"
printf '%-60s %-6s %s\n' "CHECK" "RESULT" "DETAIL"
printf '%-60s %-6s %s\n' "------------------------------------------------------------" "------" "------------------------------------------------------------"
while IFS='|' read -r check status detail; do
  [[ -n "${check}" ]] || continue
  printf '%-60s %-6s %s\n' "${check}" "${status}" "${detail}"
done <<< "${RESULTS}"
echo "============================================================"
log "restore-validate summary: PASS=${PASS} FAIL=${FAIL}"

if [[ "${FAIL}" -eq 0 ]]; then
  log "restore-validate PASSED: ${DUMP_FILE}"
  exit 0
else
  log "restore-validate FAILED: ${DUMP_FILE} (${FAIL} check(s) failed)"
  exit 1
fi
