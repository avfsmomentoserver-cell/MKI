# MKC (Momento Knowledge Core) — developer workflow.
# Everything runs against the committed venv at backend/.venv; no Docker on
# this host (deployment path: venv + uvicorn + systemd — see ops/DEPLOYMENT.md).
#
#   make install         venv check + install the backend package (editable)
#   make migrate         alembic upgrade head against the mkc database
#   make migrate-test    alembic upgrade head against the mkc_test database
#   make test            pytest -q (always runs against mkc_test)
#   make lint            ruff check src tests
#   make run             uvicorn on 127.0.0.1:8000 (local only; not run by CI)
#   make ingest ARGS=... pass-through to the mkc CLI (e.g. `mkc ingest <path>`)
#   make backup          pg_dump the mkc DB (scripts/backup.sh)
#   make restore-verify  restore + validate a dump (scripts/restore.sh;
#                        DUMP=<file> to pick one, default newest in backups/)
#   make status          mkc CLI health + status (API must be running for status)
#   make clean           remove local caches (never touches backups or .env)

# abspath: recipes cd into backend/, so tool paths must stay absolute.
VENV      := $(abspath backend/.venv)
PIP       := $(VENV)/bin/pip
UVICORN   := $(VENV)/bin/uvicorn
ALEMBIC   := $(VENV)/bin/alembic
PYTEST    := $(VENV)/bin/pytest
RUFF      := $(VENV)/bin/ruff
MKC       := $(VENV)/bin/mkc

# mkc_test DB for `make migrate-test` (overridable: make migrate-test MKC_TEST_DB_URL=...)
MKC_TEST_DB_URL ?= postgresql+psycopg://mkc:mkc@localhost:5432/mkc_test

.PHONY: install migrate migrate-test test lint run ingest backup restore-verify status clean

install:
	test -x $(VENV)/bin/python || { echo "venv missing: create it with 'python3 -m venv backend/.venv'" >&2; exit 1; }
	$(PIP) install -e ./backend

migrate:
	cd backend && $(ALEMBIC) upgrade head

migrate-test:
	cd backend && MKC_DATABASE_URL='$(MKC_TEST_DB_URL)' $(ALEMBIC) upgrade head

test:
	cd backend && $(PYTEST) -q

lint:
	cd backend && $(RUFF) check src tests

# Local/dev only: binds 127.0.0.1:8000. For service mode use ops/mkc.service.
run:
	$(UVICORN) mkc.api.app:create_app --factory --host 127.0.0.1 --port 8000 --app-dir src

ingest:
	$(MKC) ingest $(ARGS)

backup:
	./scripts/backup.sh

restore-verify:
	if [ -n "$(DUMP)" ]; then \
		./scripts/restore.sh "$(DUMP)"; \
	else \
		NEWEST=$$(ls -1t backups/mkc-*.dump 2>/dev/null | head -n1); \
		[ -n "$$NEWEST" ] || { echo "no dumps in backups/ — run 'make backup' first" >&2; exit 1; }; \
		./scripts/restore.sh "$$NEWEST"; \
	fi

# 'mkc status' requires the API to be running (it GETs /api/v1/status);
# 'mkc health' GETs /healthz. The target's exit code reflects the health probe.
status:
	$(MKC) health || true
	$(MKC) status || true
	$(MKC) health

clean:
	rm -rf .pytest_cache .ruff_cache
	find backend -type d -name '__pycache__' -exec rm -rf {} +
