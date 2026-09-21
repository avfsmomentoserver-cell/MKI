# MKC Operations Runbook

> **Status: skeleton (documentation foundation wave).** The section structure is final; body content is written in Wave 6 (devops) alongside the systemd units, backup scripts, and monitoring setup this runbook will describe. Until then, the manual commands in the root `README.md` quick-start are the current run mode. No Docker on this host — the deployment path is venv + uvicorn + systemd (verified in `ops/ENVIRONMENT.md` §6).

## 1. Starting Services

How to bring the full stack up on the host from a cold boot or after a restart: PostgreSQL 17 start and readiness check (`pg_ctlcluster 17 main start`, `PGPASSWORD=... psql -c 'SELECT 1'`), the MKC API start (current manual `uvicorn` command; the Wave 6 systemd unit name when it lands), and the verification sequence (`curl /healthz`, `mkc health`, `GET /api/v1/status`). The filled-in section will show the expected output at each step so an operator can tell at a glance which component failed, plus the correct stop order for maintenance windows (API first, then ingest, DB last).

## 2. Database Backup / Restore

The backup and restore procedure for the `mkc` PostgreSQL database: the backup command (with exact `pg_dump` flags), where backups are written and how often (scheduled in Wave 6), retention, and integrity verification after each backup. Restore covers the two scenarios — restoring into a throwaway instance to inspect, and a full restore after data loss — with post-restore checks (`alembic current`, object-count reconciliation against `GET /api/v1/status`). It will also state the key operational fact: `repos/` and `content-archive/` are re-ingestable, so a DB loss is recoverable from the source repos, which bounds the blast radius of the worst-case restore.

## 3. Monitoring

What is watched and how: the `GET /metrics` Prometheus surface (request rates/durations, ingest run counters and failures, object counts by type/lifecycle, last-ingest timestamp), the `GET /healthz` liveness check, and the structured JSON log streams. Wave 6 defines the scrape target, the alert thresholds (ingest failure streak, last-ingest staleness, error-rate spikes, DB connection exhaustion), and where alerts are delivered. This section will list each metric with its threshold and the runbook action to take when it fires.

## 4. Troubleshooting (common failures)

A symptom → diagnosis → fix table for the known failure modes: API not answering (port conflict, stale process), `mkc health` reporting DB down (PostgreSQL not running, `DATABASE_URL` mismatch in `.env`), ingest stalled or slow (repo size — `momento-avfs-core` is 831 MB with large binaries, incremental-key mismatch, a re-cloned repo with rewritten history breaking commit-hash links — the provenance-drift case from the risk register), search returning empty (full-text index not built, filter too narrow), 401 storms (token rotation mismatch between `.env` and the client), and report generation producing empty output (analysis pass not run, no corpus yet). Each entry gives the exact diagnostic command and the expected healthy output.

## 5. Deployment

The release procedure: how a new backend version goes from git to running — pull/checkout, dependency install from `backend/requirements.txt`, `alembic upgrade head` (forward-only migrations; the rule for a failed migration and when a manual DB step is required), service restart, and the post-deploy verification pass (`/healthz`, `/api/v1/status`, one search, `mkc status` count comparison). Wave 6 adds the systemd unit files, the rollback path (previous revision + previous code), and the deploy checklist in exact order, plus the dashboard static-build deploy step once `web/` exists.
