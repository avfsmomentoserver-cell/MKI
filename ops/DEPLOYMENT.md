# MKC Deployment Guide (single operator)

Target host: Debian GNU/Linux 13 (trixie), one operator account `admin`
(uid 1000, passwordless sudo). Deployment path: **venv + uvicorn + systemd**.
Every command below was executed and verified on this machine on 2026-09-21
unless marked *staged* (to be run by the operator).

---

## 1. Prerequisites (verified on this host)

| component | verified value | how it was verified |
|---|---|---|
| OS | Debian 13 (trixie) | `/etc/os-release` (baseline `ops/ENVIRONMENT.md`) |
| Postgres | 17.11, cluster `17/main`, port 5432, online | `psql --version`, `sudo -u postgres psql` |
| extensions | `hstore 1.8`, `vector 0.8.0` in `mkc` DB | `SELECT extname, extversion FROM pg_extension;` |
| role / DB | role `mkc` (LOGIN), databases `mkc` + `mkc_test` | `pg_roles`, `pg_database` queries |
| Python | system 3.13.5; app venv at `backend/.venv` (pip 26.2.1) | `./backend/.venv/bin/python --version` |
| package | `mkc 0.1.0` installed editable, CLI `mkc = mkc.cli:main` | `pip show mkc`, `backend/pyproject.toml` |
| systemd | present, `is-system-running` = running | `systemctl is-system-running` |
| Docker | **NOT installed** (`command -v docker` → nothing) | see §7 Porting notes |
| tools | `pg_dump`/`psql` 17.11, `make` 4.4.1, `pg_isready` | `--version` on each |

## 2. Setup from scratch

Run as `admin` in `/home/admin/MKI`. Steps 1–4 are *staged* (already applied
on this host; shown for a fresh machine). Steps 5–6 are verified.

```bash
# 1) Postgres + extensions (superuser)
sudo apt-get install -y postgresql postgresql-contrib postgresql-17-pgvector
sudo service postgresql start
sudo -u postgres psql -c "CREATE ROLE mkc WITH LOGIN PASSWORD '<password>';"
sudo -u postgres psql -c "CREATE DATABASE mkc OWNER mkc;"
sudo -u postgres psql -d mkc -c "CREATE EXTENSION IF NOT EXISTS hstore;"
sudo -u postgres psql -d mkc -c "CREATE EXTENSION IF NOT EXISTS vector;"
sudo -u postgres psql -c "CREATE DATABASE mkc_test OWNER mkc;"   # test DB for pytest

# 2) Environment file (values stay in .env — never in git, never printed)
cp .env.example .env       # then fill POSTGRES_*, DATABASE_URL, MKC_API_TOKEN

# 3) Python venv + package
python3 -m venv backend/.venv
make install               # == backend/.venv/bin/pip install -e backend/
```

> **Known defect (out of my scope, flag for ops):** `backend/requirements.txt`
> currently contains a pinned editable URL that embeds a live GitHub PAT
> (`-e git+https://<token>@github.com/...`). Do **not** `pip install -r` that
> file; it works today only because the venv already has the package installed
> editable. Rotate the PAT and regenerate the freeze (handoff item).

```bash
# 4) Migrations
make migrate               # alembic upgrade head against `mkc`
make migrate-test          # alembic upgrade head against `mkc_test`
make test                  # pytest -q (139 passing at time of writing)
make lint                  # ruff check src tests
```

## 3. Running the API

Local/dev (foreground, binds 127.0.0.1:8000):

```bash
make run
```

Equivalent raw command:

```bash
cd /home/admin/MKI/backend
./.venv/bin/uvicorn mkc.api.app:create_app --factory --host 127.0.0.1 --port 8000 --app-dir src
```

Health probe (public, no token): `curl -s http://127.0.0.1:8000/healthz`.
Authenticated status: `make status` (runs `mkc health` + `mkc status`;
`mkc status` GETs `/api/v1/status` with the token from `.env`, so the API
must be running).

## 4. Systemd enablement (staged — operator runs this)

Unit file: [`ops/mkc.service`](mkc.service). **Not installed or enabled by
this wave** — enable it when the API should be a resident service:

```bash
sudo cp ops/mkc.service /etc/systemd/system/mkc.service
sudo systemctl daemon-reload
sudo systemctl enable --now mkc.service
```

Verify:

```bash
systemctl status mkc.service
curl -s http://127.0.0.1:8000/healthz
journalctl -u mkc.service -f      # live logs (stdout/stderr → journal)
```

Design decisions, with evidence:

- **`EnvironmentFile=` is deliberately omitted.** `backend/src/mkc/core/config.py`
  loads the repo-root `.env` itself: `SettingsConfigDict(env_file=str(ENV_FILE_PATH))`
  (lines 50–55) and `_load_dotenv_overlays()` (lines 69–97), with an explicit
  `DATABASE_URL` fallback in `load_settings()` (lines 124–129). So the uvicorn
  process gets everything it needs from the code path alone. systemd's
  EnvironmentFile parser handles quotes/comments differently from pydantic's;
  keeping exactly one consumer of `.env` avoids divergence. Add
  `Environment=MKC_ENV=prod` style lines in the unit if you ever need
  process-only vars.
- `User=admin`, `WorkingDirectory=/home/admin/MKI/backend`,
  `ExecStart=.../backend/.venv/bin/uvicorn mkc.api.app:create_app --factory
  --host 127.0.0.1 --port 8000 --app-dir src`, `Restart=on-failure`,
  `RestartSec=5`, `After=postgresql.service`, `Wants=postgresql.service`.
- Note: a prior draft unit lives at `ops/systemd/mkc-api.service` (different
  name, includes `EnvironmentFile`, no `--app-dir src`). The canonical unit
  going forward is `ops/mkc.service`; the old draft is superseded and left
  untouched (another agent may reference it).

## 5. Backup / restore operations

### Rule

> **A backup that has never been restored is not considered validated.**

So: run a backup, then validate it with a real restore into a throwaway DB.

### Backup

```bash
make backup                 # == ./scripts/backup.sh
```

- `pg_dump -Fc` (custom format) of the `mkc` database only.
- Output: `backups/mkc-YYYYmmdd-HHMMSS.dump` (override dir: `MKC_BACKUP_DIR`).
- Credentials: `PG*`/`PGPASSWORD` env if set, else `DATABASE_URL` parsed from
  the repo `.env`. The password is never printed: pg_dump output goes to a
  scratch file; on failure the logged excerpt is redacted.
- Log: `backups/backup.log` (timestamped, secret-free; verify with
  `grep -F 'user:pass@' backups/backup.log` → no match).
- Retention: newest **30** dumps kept; each pruned file is logged.
- `set -euo pipefail`; a failed dump leaves no partial `.dump` (tmp + rename).

When to run: before migrations, before risky ingest waves, and on a schedule
(e.g. daily via cron — scheduling is a follow-up, not wired in this wave).

### Restore validation

```bash
make restore-verify                     # newest dump in backups/
make restore-verify DUMP=backups/mkc-XXXX.dump   # a specific dump
```

`scripts/restore.sh <dump>` restores the dump into the throwaway database
`mkc_restore_verify` (created if absent, **dropped on exit including failure**
via trap) and prints a PASS/FAIL table. Checks:

1. `alembic_version` in the restored DB equals the live `mkc` DB head;
2. row counts for all 12 content tables
   (`sources, documents, knowledge_objects, entities, entity_relations,
   research_items, decisions, experiments, insights, contradictions,
   audit_log, reports`) equal the live DB's counts;
3. 3 random `knowledge_objects` rows (by id) have a non-empty JSONB
   `provenance` with keys `source_type` / `source_location` / `extraction_method`;
4. if `decisions` has rows, one full decision row exists in the restored DB
   (skipped with a note otherwise).

Exit 0 only if every check passes. The restore runs as the `postgres`
superuser (the dump embeds extension DDL only a superuser can execute); the
read checks run as the app role `mkc` (realistic read path).

**Caveat — live-writer skew:** if another agent is writing to `mkc` between
the dump and the count checks, table counts can differ and the run will
correctly FAIL. Run during a quiet window; re-run when it fails for this
reason. (Observed during authoring: an ingest pass wrote 3 sources + 497
documents between one dump and its verification; the immediate retry was
clean 15/15 PASS.)

### Real disaster recovery (manual)

The validated path is the same one the script uses:

```bash
sudo -u postgres dropdb --if-exists mkc && sudo -u postgres createdb -O mkc mkc
sudo -u postgres pg_restore --exit-on-error --dbname=mkc backups/mkc-XXXX.dump
# then: make migrate (no-op if at head), restart the API, make restore-verify DUMP=...
```

## 6. CI

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) — single `test`
job, on push/PR to `main`:

1. `actions/checkout` + `setup-python 3.12` (pip cache keyed on
   `backend/pyproject.toml`);
2. service container `pgvector/pgvector:pg17` with
   `POSTGRES_USER=mkc POSTGRES_PASSWORD=mkc POSTGRES_DB=mkc_test`, plus an
   explicit `pg_isready` wait loop (the container healthcheck is only a
   head-start);
3. `pip install -e "backend[dev]"` (dev extra = pytest + ruff; httpx is core);
4. `alembic upgrade head` + `alembic current` against the clean `mkc_test`
   (proves the migration chain applies from scratch — the initial migration
   `3efd7b1a065c` uses only built-in types, so no extension setup is needed);
5. `ruff check src tests`;
6. `pytest -q` (conftest forces `MKC_DATABASE_URL` to the `mkc_test` DB and
   asserts the name contains `mkc_test` — CI can never touch production).

No secrets are required. **Honesty note:** this box has no GitHub Actions
runner and no Docker, so the workflow cannot be executed here — it is
exercised on the GitHub remote only. It will start running on the next push
to `main` once the repo has Actions enabled.

## 7. Rollback

**Forward-only migrations.** `alembic downgrade` is **NOT a supported
rollback path** for schema: no migration currently has a tested downgrade,
and downgrading the schema under a live app risks data loss.
`docs/OPS_RUNBOOK.md` (wave-6 section, skeleton — body being written by the
docs wave alongside this guide) is where the full release/rollback runbook
lives; it states the same forward-only rule.

What *is* supported:

- **Code rollback:** check out the previous release tag/commit,
  `make install`, restart the service (`sudo systemctl restart mkc.service`
  once enabled). Migrations only forward; the older code must run against
  the newer schema — verify with `make test` before rolling back.
- **Data rollback:** restore the most recent *validated* dump
  (§5) — which is exactly why the restore-validation rule exists.

## 8. Porting notes: why venv + uvicorn + systemd (no Docker)

- `command -v docker` → not found; `sudo docker info` → command not found
  (verified 2026-09-20, `ops/ENVIRONMENT.md` §6, re-checked 2026-09-21).
- Docker is **not available on this host** and installing a container runtime
  is out of scope for the deployment wave.
- The app is a single Python process + a single local Postgres: a systemd
  unit over the committed venv is the smallest, most observable deployment
  (journald logs, `Restart=on-failure`, `systemctl status`). CI uses the
  `pgvector/pgvector:pg17` container image on GitHub runners, so Postgres
  parity between dev and CI holds without Docker locally.
- If Docker ever lands on this host, the same `pgvector/pgvector:pg17` image
  and the same unit's `ExecStart` command map directly to a container entry.

## 9. Quick reference

| task | command |
|---|---|
| install / reinstall package | `make install` |
| migrate prod / test DB | `make migrate` / `make migrate-test` |
| tests / lint | `make test` / `make lint` |
| run API (dev) | `make run` |
| health + status | `make status` (API must be up for `status`) |
| backup | `make backup` |
| validate latest / given dump | `make restore-verify` / `make restore-verify DUMP=<file>` |
| enable service (staged) | §4 block |
| ingest a source | `make ingest ARGS='<path>'` |
