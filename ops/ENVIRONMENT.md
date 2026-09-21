# MKC Environment Baseline

Generated: 2026-09-20 (wave 0 — environment foundation)
Host: Debian GNU/Linux 13 (trixie), user `admin` (uid 1000, sudo group, passwordless sudo)
Workspace: `/home/admin/MKI` (clone of `avfsmomentoserver-cell/MKI`, branch `main`)

This document is the single source of truth for reproducing the local development
environment. Every value below was verified by running the stated command on this machine.

---

## 1. Git state

- Repo: `/home/admin/MKI`
- Remote origin: `https://<token>@github.com/avfsmomentoserver-cell/MKI.git` (PAT embedded in remote URL; works for fetch/push)
- Local git identity: `user.name = "MKC Build"`, `user.email = "mkc-build@local"` (repo-local config)
- Branch: `main`
- Baseline commit: `fd9fc25 baseline: workspace snapshot` (pushed to `origin main`)
- `.gitignore` ignores: `repos/`, `content-archive/`, `*.db`, `*.sqlite*`, `data/`, `logs/`, `__pycache__/`, `.venv/`, `backend/.venv/`, `backend/instance/`, `node_modules/`, `.env` (`.env.example` is tracked)
- Staged at baseline: only `.gitignore` + `file-master-index.json` (~385 KB total — far under the 30 MB threshold)
- `repos/` = 1.3 GB, `content-archive/` = 292 MB — both gitignored, never committed

Reproduce:

```bash
cd /home/admin/MKI
git remote set-url origin https://<PAT>@github.com/avfsmomentoserver-cell/MKI.git
git config user.name "MKC Build"
git config user.email "mkc-build@local"
```

## 2. PostgreSQL

- Package: `postgresql` 17.11 (Debian 17.11-0+deb13u1), installed via `apt-get install -y postgresql postgresql-contrib`
- Plus: `postgresql-17-pgvector` (for the `vector` extension)
- Cluster: `17/main` on port **5432**, status **online** (Debian manages it; `service postgresql start` / `pg_ctlcluster 17 main start` to restart if needed)
- Role: `mkc` (LOGIN, password `CHANGE_ME`)
- Database: `mkc` (owner `mkc`)
- Extensions in `mkc` DB: `hstore 1.8`, `vector 0.8.0` (pgvector), `plpgsql 1.0`

### Connection details

| Field      | Value                                        |
|------------|----------------------------------------------|
| Host       | `localhost`                                  |
| Port       | `5432`                                       |
| User       | `mkc`                                        |
| Password   | `CHANGE_ME`                                        |
| Database   | `mkc`                                        |
| psql URL   | `postgresql://mkc:CHANGE_ME@localhost:5432/mkc`    |
| SQLAlchemy | `postgresql+psycopg://mkc:CHANGE_ME@localhost:5432/mkc` |

Verified: `PGPASSWORD=CHANGE_ME psql -h localhost -U mkc -d mkc -c 'SELECT 1'` → returned `1`.

Create role/DB from scratch (as superuser `postgres`):

```bash
sudo -u postgres psql -c "CREATE ROLE mkc WITH LOGIN PASSWORD 'CHANGE_ME';"
sudo -u postgres psql -c "CREATE DATABASE mkc OWNER mkc;"
sudo -u postgres psql -d mkc -c "CREATE EXTENSION IF NOT EXISTS hstore;"
sudo -u postgres psql -d mkc -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

> Note: `vector` requires `postgresql-17-pgvector` (`apt-get install -y postgresql-17-pgvector`)
> and must be created by a superuser. `hstore` alone is not enough for vector columns.

## 3. `.env` / `.env.example`

- `/home/admin/MKI/.env` — real values (gitignored):

```ini
POSTGRES_HOST=localhost
POSTGRES_USER=mkc
POSTGRES_PASSWORD=CHANGE_ME
POSTGRES_DB=mkc
DATABASE_URL=postgresql+psycopg://mkc:CHANGE_ME@localhost:5432/mkc
MKC_API_TOKEN=CHANGE_ME
```

- **`MKC_API_TOKEN` = `CHANGE_ME`** (40-char hex, generated with `openssl rand -hex 20`).
  This is the local dev shared secret for the MKC REST API; it stays on this machine and in this
  gitignored file. Any service/client that needs API access reads it from `.env`.
- `/home/admin/MKI/.env.example` — committed template with `CHANGE_ME` placeholders. Copy with
  `cp .env.example .env` and fill in values to bootstrap a fresh clone.

## 4. Python environment

- System Python: **3.13.5** (`/usr/bin/python3`) — exceeds the 3.12 minimum
- Venv: **`/home/admin/MKI/backend/.venv`** (created with `python3 -m venv backend/.venv`)
- `backend/requirements.txt` did **not** exist, so the core set was installed directly:
  `psycopg[binary] sqlalchemy alembic pydantic pydantic-settings fastapi httpx uvicorn pytest pytest-cov ruff`
  The backend wave should pin the final set into `backend/requirements.txt` from the freeze below.

### Key package versions (pip 26.2.1)

| Package              | Version |
|----------------------|---------|
| SQLAlchemy           | 2.0.54  |
| fastapi              | 0.141.1 |
| pydantic             | 2.13.5  |
| pydantic-settings    | 2.15.0  |
| psycopg (3)          | 3.3.6   |
| psycopg-binary       | 3.3.6   |
| alembic              | 1.20.0  |
| httpx                | 0.28.1  |
| uvicorn              | 0.53.0  |
| pytest               | 9.1.1   |
| pytest-cov           | 7.1.0   |
| ruff                 | 0.16.8  |
| starlette            | 1.6.0   |
| Mako                 | 1.4.1   |

### Full `pip freeze` (33 packages)

```
alembic==1.20.0
annotated-doc==0.0.5
annotated-types==0.8.0
anyio==4.15.1
certifi==2026.7.22
click==8.5.0
coverage==7.16.1
fastapi==0.141.1
greenlet==3.5.6
h11==0.16.0
httpcore==1.0.9
httpx==0.28.1
idna==3.20
iniconfig==2.3.0
Mako==1.4.1
MarkupSafe==3.0.3
packaging==26.3
pluggy==1.6.0
psycopg==3.3.6
psycopg-binary==3.3.6
pydantic==2.13.5
pydantic-settings==2.15.0
pydantic_core==2.46.5
Pygments==2.21.0
pytest==9.1.1
pytest-cov==7.1.0
python-dotenv==1.2.3
ruff==0.16.8
SQLAlchemy==2.0.54
starlette==1.6.0
typing-inspection==0.4.4
typing_extensions==4.16.0
uvicorn==0.53.0
```

### Verified import + live DB round-trip

```
$ ./backend/.venv/bin/python -c "import sqlalchemy, fastapi, pydantic, psycopg, alembic; print('imports OK')"
imports OK
$ ./backend/.venv/bin/python -c "import psycopg; ..."   # connects to mkc DB
DB round-trip: PostgreSQL 17.11 (Debian 17.11-0+deb13u1
extensions: ['hstore', 'vector']
```

Reproduce the venv:

```bash
cd /home/admin/MKI
python3 -m venv backend/.venv
./backend/.venv/bin/pip install --upgrade pip
./backend/.venv/bin/pip install "psycopg[binary]" sqlalchemy alembic pydantic pydantic-settings \
    fastapi httpx uvicorn pytest pytest-cov ruff
# pin after the backend wave finalizes requirements:
./backend/.venv/bin/pip freeze > backend/requirements.txt
```

## 5. Source repo health (`/home/admin/MKI/repos/`, 11 clones)

All 11 are valid git clones. "Meaningful" = has committed content and non-trivial source.

| Repo               | Tracked files | Size   | Latest commit (short)                                              | Assessment                    |
|--------------------|--------------:|--------|--------------------------------------------------------------------|-------------------------------|
| avfs-backend       | 3             | 224K   | `45ca018` Merge PR #1 (sandbox/lesq)                                | Skeleton (3 files)            |
| azuredev-3867      | 0             | 124K   | none — branch `main` has no commits yet                             | **Empty** (no commits)        |
| InvestigationSuite | 29            | 272M   | `b6d0a898` Merge PR #1 (from-spaces)                                | Meaningful (large assets)     |
| momento-avfs-core  | 406           | 831M   | `6021d33` Update .gitignore: exclude large backup files             | Meaningful (largest, has big binaries) |
| momento-core       | 764           | 24M    | `bbbf246` Merge PR #4 (Library)                                     | Meaningful                    |
| momento-core3      | 15            | 4.5M   | `7c1121e` feat: core prediction pipeline, forecast engine, live streaming | Meaningful (compact, focused) |
| momentocore2       | 66            | 680K   | `80fad7e` feat: core storage, API server, feature extraction        | Meaningful                    |
| MomentoFresh       | 96            | 1016K  | `35f0145` Merge PR #1 (feature/stride-integration)                  | Meaningful                    |
| MomentoFX          | 726           | 25M    | `a529e84` Add files via upload                                      | Meaningful                    |
| MomentoRabbit      | 2             | 8.7M   | `0b060d5` Add files via upload                                      | Skeleton (2 files, mostly a large blob) |
| MomentoV5          | 508           | 105M   | `4e279a6` Initial project setup with full MomentoV5 platform        | Meaningful                    |

**Empty/skeleton:** `azuredev-3867` (no commits), `avfs-backend` (3 files), `MomentoRabbit` (2 files, one large blob).
**Solid ingestion targets for MKC:** `momento-core`, `MomentoFX`, `MomentoV5`, `momento-core3`, `momentocore2`, `MomentoFresh`, `InvestigationSuite`, `momento-avfs-core`.

Reproduce the health table:

```bash
cd /home/admin/MKI/repos
for d in */; do d=${d%/}; \
  git -C "$d" log --oneline -1; \
  echo "files=$(git -C "$d" ls-files | wc -l) size=$(du -sh "$d" | cut -f1)"; \
done
```

## 6. Docker

- `command -v docker` → **NOT FOUND**
- `docker --version` → not available; `sudo docker info` → `sudo: docker: command not found`
- Verdict: **docker deployment deferred — venv + uvicorn + systemd plan instead.**
  (systemd is present and `is-system-running` → `running`, so a systemd unit for uvicorn is the deployment path.)

## 7. Reproduction checklist (backend / QA waves)

```bash
# 1. Workspace + git
cd /home/admin/MKI
git pull --ff-only
git config user.name "MKC Build"
git config user.email "mkc-build@local"

# 2. Postgres (install only once)
sudo apt-get install -y postgresql postgresql-contrib postgresql-17-pgvector
sudo service postgresql start            # or: sudo pg_ctlcluster 17 main start
sudo -u postgres psql -c "CREATE ROLE mkc WITH LOGIN PASSWORD 'CHANGE_ME';"      # if absent
sudo -u postgres psql -c "CREATE DATABASE mkc OWNER mkc;"                  # if absent
sudo -u postgres psql -d mkc -c "CREATE EXTENSION IF NOT EXISTS hstore;"
sudo -u postgres psql -d mkc -c "CREATE EXTENSION IF NOT EXISTS vector;"
PGPASSWORD=CHANGE_ME psql -h localhost -U mkc -d mkc -c 'SELECT 1'               # expect 1

# 3. Env vars
cp -n .env.example .env                 # then fill values (or use the existing .env)

# 4. Python
python3 -m venv backend/.venv
./backend/.venv/bin/pip install --upgrade pip
./backend/.venv/bin/pip install -r backend/requirements.txt   # once the backend wave adds it
# until then:
./backend/.venv/bin/pip install "psycopg[binary]" sqlalchemy alembic pydantic pydantic-settings \
    fastapi httpx uvicorn pytest pytest-cov ruff

# 5. Run the API (uvicorn, no docker)
./backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 8. Evidence snapshot

- `git log` (last commit at time of writing): `fd9fc25 baseline: workspace snapshot`
- `SELECT 1`: returned `1`
- Python import test: `imports OK` (sqlalchemy 2.0.54, fastapi 0.141.1, pydantic 2.13.5)
- Extensions present in `mkc` DB: `hstore 1.8`, `vector 0.8.0`, `plpgsql 1.0`
