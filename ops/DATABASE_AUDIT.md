# MKC Database Audit — Verification Snapshot

- **Date:** 2026-09-20 (23:26–23:35 UTC, host time)
- **Scope:** Postgres 17.11 (`17/main`, port 5432) network/auth state (threat-model items **T-E2 / T-P4**), file-permission findings, git-history secret-exposure verdict (**T-X3**), and a full backup → restore → reconciliation cycle for the `mkc` database.
- **Status:** verification snapshot only. **No live configuration was changed.** §5 stages the exact commands for the Wave 5/6 security fix to apply atomically.
- **Constraints honored:** no live Postgres config changes, no `chmod` on `.env` (staged, §5), the temp database `mkc_restore_test` was created, used, and dropped. The two live backend agents were not touched; the live DB was only read from (`COUNT(*)` queries).
- **No-secrets rule:** this document references credential values by location and shape only, never by value.

---

## 1. Postgres state (T-E2 / T-P4)

### 1.1 `postgresql.conf` (`/etc/postgresql/17/main/postgresql.conf`)

```conf
#listen_addresses = 'localhost'     # line 60 — commented → default 'localhost'
port = 5432                          # line 64
max_connections = 100                # line 65
unix_socket_directories = '/var/run/postgresql'   # line 68
#log_statement = 'none'              # line 622 — commented → default 'none'
#log_min_duration_statement = -1     # line 547 — commented → default -1 (off)
```

- `listen_addresses` is **not set** → effective value is the built-in default **`localhost`**.
- Statement logging: **both `log_statement` and `log_min_duration_statement` are at defaults = disabled.**
- `conf.d/` is empty (no drop-in overrides).

### 1.2 Observed sockets (corroborates config)

```text
LISTEN  127.0.0.1:5432
LISTEN  [::1]:5432
```

Loopback only (v4 + v6). No external-interface listener. **FACT: the server accepts connections only from this host.**

### 1.3 `pg_hba.conf` (exact effective lines, no secrets in these lines)

```conf
local   all             postgres                                peer
local   all             all                                     peer
host    all             all             127.0.0.1/32            scram-sha-256
host    all             all             ::1/128                 scram-sha-256
local   replication     all                                     peer
host    replication     all             127.0.0.1/32            scram-sha-256
host    replication     all             ::1/128                 scram-sha-256
```

- **(a) TCP 127.0.0.1 / ::1, role `mkc`:** effective method = **`scram-sha-256`** (via the generic `host all all 127.0.0.1/32` / `::1/128` lines). Good.
- **(b) Local socket lines:** `local all postgres peer` (superuser) and `local all all peer`. The `peer` line means **any OS user whose name matches an existing DB role can connect as that role with no password.**

### 1.4 Role state (`sudo -u postgres psql`)

| role | login | password verifier | method |
|---|---|---|---|
| `mkc` | yes | **set, `SCRAM-SHA-256…`** (133-char stored verifier) | scram-sha-256 |
| `postgres` | yes | none (peer-only superuser) | — |

`\du+` equivalents confirmed via `pg_authid`: `mkc` has a password set, stored as a SCRAM-SHA-256 verifier. The `postgres` superuser has no password (as intended — it is reachable only via `peer` + sudo).

**Weakness:** the `mkc` password is a weak 3-character value and its exact value is printed in a tracked doc (see §3). The stored verifier is SCRAM, so the weak password itself is not in the file system outside the committed doc and `.env`.

### 1.5 Verdict — can a local non-`admin` user reach the DB? (T-E2)

**Currently: NO — by the single fact that `admin` (uid 1000) is the only normal OS user on the box.**

```text
$ getent passwd | awk -F: '$3>=1000 && $3<65000'   →  admin (uid 1000) only
```

**If/when a second local account exists: YES, trivially, on two independent paths** (until §5 is applied):

1. **Peer path (socket):** the `local all all peer` line lets a local user log into Postgres as any role whose name matches the OS username — no password at all. Creating a DB role with a matching name (or simply adding an OS user named `mkc`) yields full `mkc` access with zero credentials. This is the cleaner hole.
2. **Password path (TCP):** any local process can open `127.0.0.1:5432` and authenticate as `mkc` with the weak password, which is *printed in the committed doc* (`ops/ENVIRONMENT.md`, §3 below) and world-readable on disk (`.env` mode 664, §2).

So T-E2 is **latent, not active**: reachability is currently blocked only by absence of a second local user, not by configuration. The staged fix in §5 (steps 1–2) closes path 1; step 3 (rotation) closes path 2.

---

## 2. File permission findings

Recorded 2026-09-20 23:26. `stat` output, verbatim where shown.

| path | mode | owner | target | status |
|---|---|---|---|---|
| `/home/admin/MKI/.env` | **664** | admin:admin | 600 | **FAIL — group/world readable** (staged fix §5 step 6; do NOT fix out-of-band) |
| `/home/admin/MKI/.git/config` | **664** | admin:admin | 600 | **FAIL — world-readable; embeds the GitHub PAT in `remote.origin.url`** (staged fix §5 step 6) |
| `/home/admin/MKI/.env.example` | 664 | admin:admin | 644 ok | OK (placeholders only — verified `CHANGE_ME`) |
| `/home/admin/MKI/.gitignore` | 664 | admin:admin | — | OK (no secrets); **`backups/` line was missing — added during this audit** |
| `/etc/postgresql/17/main/pg_hba.conf` | 640 | postgres:postgres | — | OK |
| `/home/admin/MKI/backups/` | 700 (this audit) | admin:admin | 700 | created by this audit; dump file set 600 |

- All other top-level files in `/home/admin/MKI/` are mode 664, owner `admin:admin`; none contain secrets (verified by the shape grep in §3.3: no 40-hex or `glpat-` strings outside the listed files).
- Note: with only `admin` on the host, a world-readable `.env`/`.git/config` is not exploitable *today*, but it breaks the least-privilege baseline the moment a second local user exists, and it is what makes the T-E2 password path one `cat` away.
- The PAT embedded in `.git/config` is **on disk only — it is not in git history** (verified in §3: no `glpat-`/40-hex string in any tracked file other than the MKC token; the remote URL line in `ops/ENVIRONMENT.md` is the placeholder `<token>`, not the real PAT).

## 3. T-X3 — git-history secret exposure verdict

Commands run (all `git -C /home/admin/MKI`):

```text
$ git log --all --oneline -- .env
(empty — exit 0)                       → .env itself was NEVER committed

$ git log --all --oneline -- ops/ENVIRONMENT.md
4b0877e ops: environment baseline report and env template

$ git remote -v                        (token masked)
origin  https://***@github.com/avfsmomentoserver-cell/MKI.git  (fetch/push)

$ git log --oneline                     full local history
4b0877e ops: environment baseline report and env template
fd9fc25 baseline: workspace snapshot

$ git ls-remote origin main            (live remote check, not just local ref)
4b0877e4270ffdbecf680d476a9a1d13ddc9ebc5   refs/heads/main
```

### 3.1 Verdict

> **T-X3 = PUSHED-TO-REMOTE.**
> The secret-bearing commit `4b0877e` (containing `ops/ENVIRONMENT.md`) is the tip of `main` **on the live GitHub remote** (verified against `ls-remote`, not just the local `origin/main` ref). `git status` shows a clean tree relative to `main` (untracked: `backend/`, `docs/`, `web/`, `README.md`, `CHANGELOG.md` — none committed).

Consequences:

- **Rotation alone is necessary but NOT sufficient.** The committed values (40-hex API token, DB password) remain readable by anyone who can read the GitHub repo or the PAT in `.git/config`. History must be purged (force-push rewrite of the two-commit history — trivial at this size — or repo deletion/recreate) **and** the GitHub PAT revoked, as the threat model (mitigation #1) already requires.
- **Corroboration, measured:** the 40-hex `MKC_API_TOKEN` in the pushed commit is **byte-identical** to the one in the live `.env` (compared in-memory via `first4/last4` + full-hash; values not printed). The committed doc's 3-character DB password is also byte-identical to `POSTGRES_PASSWORD` in `.env`. So the pushed history contains **live, working credentials**, not stale ones.

### 3.2 Tracked files that print real credentials (inventory, masked)

Full tree, `git grep` (tracked files only):

| file:line(s) | what is printed | shape |
|---|---|---|
| `ops/ENVIRONMENT.md:77` | `MKC_API_TOKEN=c395…b993` | 40-hex |
| `ops/ENVIRONMENT.md:80` | same token restated in prose | 40-hex |
| `ops/ENVIRONMENT.md:37, 48, 50, 51, 53, 58, 74, 223, 227` | the `mkc` DB password printed in prose, the connection table, two connection URLs, and the reproduction SQL (`CREATE ROLE … PASSWORD '<pw>'`, `PGPASSWORD=<pw> psql …`) | 3-char weak password (value = role name) |
| `.env.example:7, 14` | `POSTGRES_PASSWORD=CHANGE_ME`, `MKC_API_TOKEN=CHANGE_ME` | **benign** (placeholders) |
| `ops/ENVIRONMENT.md:15, 27` | `https://<token>@github.com/…` | placeholder, **not** the real PAT — benign |

**That is the complete set for tracked files.** No other tracked file contains a 40-hex or `glpat-` string (checked).

### 3.3 Untracked / on-disk corroboration (same grep, `--hidden`, excluding `repos/`, `content-archive/`, `node_modules/`)

- `.env` (gitignored, untracked) — contains the same 40-hex token (first4 `c395`, last4 `b993`) + the 3-char DB password. Real values, on disk, mode 664 (§2).
- No `glpat-*` strings anywhere outside the gitignored `repos/` archive. (The threat model's two `glpat-` tokens live in `repos/momento-core/`, which is gitignored in *this* repo — exposure there is via the GitLab remote's own history, per THREAT_MODEL.md mitigation #1; out of scope for this audit.)

---

## 4. Backup / restore verification

Spec rule applied: *"a backup that has never been restored is not validated."*

### 4.1 Exact commands

```bash
mkdir -p /home/admin/MKI/backups                                    # created (was absent)
sudo -u postgres pg_dump -Fc mkc > /home/admin/MKI/backups/mkc-20260920-233132.dump
sudo -u postgres dropdb --if-exists mkc_restore_test
sudo -u postgres createdb -O mkc mkc_restore_test
sudo -u postgres psql -d mkc_restore_test -c \
  "CREATE EXTENSION IF NOT EXISTS hstore; CREATE EXTENSION IF NOT EXISTS vector;"
time sudo -u postgres pg_restore --dbname=mkc_restore_test mkc-20260920-233132.dump
# …reconciliation queries (COUNT(*) per table, both sides)…
sudo -u postgres dropdb mkc_restore_test
```

Note: the restore ran as the `postgres` superuser (not as role `mkc`) so that extension/toc-level objects restore cleanly. This is the same privilege level a real disaster-recovery operator would use; it does not weaken the validation.

### 4.2 Results

| item | value |
|---|---|
| dump file | `/home/admin/MKI/backups/mkc-20260920-233132.dump` |
| dump format | custom (`-Fc`) |
| **dump size** | **57,175 bytes** |
| dump duration | <1 s (8.4 MB live DB) |
| **restore duration** | **0.132 s wall** (`pg_restore` exit 0, zero errors in output) |
| extensions in dump | **yes — both present as TOC entries**: `EXTENSION hstore` + `EXTENSION vector` (verified with `pg_restore --list`). Restore-side DB confirmed `hstore 1.8`, `vector 0.8.0`. The manual `CREATE EXTENSION` before `pg_restore` made the dump's extension objects restore as no-ops; a bare `createdb` without them would also have been restored correctly because the DDL is in the dump — but keeping the explicit create is the safer convention and is kept in the DR runbook. |
| tables restored | 13/13 base tables in `public` |
| temp DB | `mkc_restore_test` **dropped**; `pg_database` now shows `mkc`, `mkc_test` only (the latter pre-existing, owned/used by another agent — untouched) |

### 4.3 Reconciliation

Count query (identical on both sides, at t0 = just before dump / just after restore):

```sql
SELECT 'sources', count(*) FROM public.sources
UNION ALL SELECT 'documents', count(*) FROM public.documents
UNION ALL SELECT 'knowledge_objects', count(*) FROM public.knowledge_objects
UNION ALL SELECT 'entities', count(*) FROM public.entities
UNION ALL SELECT 'entity_relations', count(*) FROM public.entity_relations
UNION ALL SELECT 'research_items', count(*) FROM public.research_items
UNION ALL SELECT 'decisions', count(*) FROM public.decisions
UNION ALL SELECT 'experiments', count(*) FROM public.experiments
UNION ALL SELECT 'insights', count(*) FROM public.insights
UNION ALL SELECT 'contradictions', count(*) FROM public.contradictions
UNION ALL SELECT 'audit_log', count(*) FROM public.audit_log
UNION ALL SELECT 'reports', count(*) FROM public.reports
UNION ALL SELECT 'alembic_version', count(*) FROM public.alembic_version;
```

| table | dump-time (live t0) | restore-side | live after (t1) | match |
|---|---:|---:|---:|---|
| sources | 0 | 0 | 0 | ✔ |
| documents | 0 | 0 | 0 | ✔ |
| knowledge_objects | 0 | 0 | 0 | ✔ |
| entities | 0 | 0 | 0 | ✔ |
| entity_relations | 0 | 0 | 0 | ✔ |
| research_items | 0 | 0 | 0 | ✔ |
| decisions | 0 | 0 | 0 | ✔ |
| experiments | 0 | 0 | 0 | ✔ |
| insights | 0 | 0 | 0 | ✔ |
| contradictions | 0 | 0 | 0 | ✔ |
| audit_log | 0 | 0 | 0 | ✔ |
| reports | 0 | 0 | 0 | ✔ |
| alembic_version | 1 | 1 | 1 | ✔ |

**Verdict: PASS** — every restore-side count equals its dump-time count (13/13 tables).

*Caveat (expected, recorded per spec):* two backend agents are writing to the live `mkc` concurrently. No writes landed between t0 and t1, so the live-after column equals the dump-time column here. **This cycle validated an empty-dataset round-trip** — the meaningful schema+extensions+TOC path, but the first *populated* reconciliation should be re-run once the ingest agents have written real rows (same commands, §4.1). Recommend re-running weekly or after each major ingest wave.

---

## 5. Staged hardening (for the security wave — apply atomically, in order)

**Nothing below has been applied.** Steps 1→7 are one atomic batch (single maintenance window, verify after step 7). Steps 8→11 are the optional read-only role and can ride the same batch.

> Precondition: coordinate with the two live API agents — steps 3+4 restart the API with new credentials. Do not run steps 1–4 while the ingest pipeline is mid-write without a drain.

```bash
# 1) pg_hba.conf: close the generic peer hole. Edit /etc/postgresql/17/main/pg_hba.conf —
#    replace the line:
#        local   all             all                                     peer
#    with:
#        local   all             mkc                                     peer
#    (keep `local all postgres peer` and the three host lines as-is; they are already
#    scram-sha-256 loopback-only.) Net effect: local socket auth as `mkc` only for the
#    OS user `mkc` (none exists — so effectively only via TCP+SCRAM), superuser stays
#    peer-only. No other role is socket-reachable by name-matching.

# 2) Apply + confirm:
sudo service postgresql reload
sudo -u postgres psql -Atc "SELECT line_number, type, array_to_string(database,','), \
     array_to_string(user_name,','), address, auth_method, error \
     FROM pg_hba_file_rules ORDER BY line_number;"
#    expect: no row with error != NULL; `local/all/mkc/peer` present; no `local/all/all/peer`.

# 3) Rotate the mkc DB password (value never written to any file by this command):
NEWPW=$(openssl rand -hex 20)
sudo -u postgres psql -qc "ALTER ROLE mkc PASSWORD '$NEWPW';"
#    $NEWPW is in this shell only; the next step moves it into .env before it is lost.

# 4) Atomically update /home/admin/MKI/.env: rewrite POSTGRES_PASSWORD and DATABASE_URL
#    (the embedded mkc:password@ pair) with $NEWPW in a single edit, e.g.:
#      sed -i -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$NEWPW/" \
#             -e "s#^DATABASE_URL=postgresql+psycopg://mkc:[^@]*@#DATABASE_URL=postgresql+psycopg://mkc:$NEWPW@#" \
#             /home/admin/MKI/.env
#    then restart the API service(s) so they load the new credential.
#    POST-VERIFY (before dropping $NEWPW from the shell):
#      PGPASSWORD="$NEWPW" psql -h 127.0.0.1 -U mkc -d mkc -Atc "SELECT 1"   # expect 1
#    The committed weak password is now dead everywhere except the to-be-purged history.

# 5) Statement logging (T-P4 forensics): append to postgresql.conf (or conf.d/mkc-logging.conf):
#      log_statement = 'ddl'
#      log_min_duration_statement = 500
#    then: sudo service postgresql reload
#    (ddl-only keeps the log small; raise to 'mod' for the wave-after-ingest investigation window.)

# 6) File permissions:
chmod 600 /home/admin/MKI/.env
chmod 600 /home/admin/MKI/.git/config

# 7) Re-verify §1.5 paths are closed:
#    - no local OS user named mkc exists (getent passwd mkc → not found)
#    - listen_addresses still unset/localhost; ss -ltn shows only 127.0.0.1:5432 + [::1]:5432
#    - psql -h 127.0.0.1 -U mkc -d mkc with the OLD weak password → must FAIL (password auth failed)
```

Optional read-only role for the dashboard / future read clients (same batch, non-disruptive):

```bash
# 8) Create read-only login role:
sudo -u postgres psql -d mkc -qc "
  CREATE ROLE mkc_readonly WITH LOGIN PASSWORD '$(openssl rand -hex 20)';
  REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
  GRANT USAGE ON SCHEMA public TO mkc_readonly;
  GRANT SELECT ON ALL TABLES IN SCHEMA public TO mkc_readonly;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO mkc_readonly;"
#    (add its pg_hba line if the dashboard connects over TCP from 127.0.0.1 — it is already
#    covered by the existing `host all all 127.0.0.1/32 scram-sha-256` line, so no hba change needed)

# 9) (optional, stricter) also revoke information_schema exposure for the readonly role:
#    REVOKE SELECT ON information_schema.tables FROM PUBLIC;  # Postgres 15+ baseline: PUBLIC
#    has no default grants — only needed if a grant was ever added; check first:
#    SELECT grantee, privilege_type FROM information_schema.role_table_grants WHERE table_name='tables';

# 10) Verify read-only behavior: connect as mkc_readonly; expect
#     SELECT 1 → ok;  INSERT ... → "permission denied for table ...".

# 11) Record the new state in docs/OPS_RUNBOOK.md (threat model item 10 requires the verified
#     config to live there); note that backups/ and its dumps are gitignored and kept at 700/600.
```

Also staged for the security wave (separate from the Postgres batch — these are the T-X3 remote-side actions, owner = operator):

```bash
# A) Rotate MKC_API_TOKEN: NEW_TOKEN=$(openssl rand -hex 20); rewrite .env (single edit, step-4 style);
#    restart API; verify with one authenticated request.
# B) Revoke the GitHub PAT embedded in .git/config (GitHub → Settings → Tokens), then re-add the
#    remote with a token that has the minimum scopes (repo on this repo only) — or migrate to
#    SSH / `gh` credential helper so no token is ever stored in .git/config.
# C) Purge pushed history (T-X3 verdict is PUSHED-TO-REMOTE): history is exactly 2 commits, so the
#    cheapest safe purge is repo delete + re-init from the scrubbed tree (ops/ENVIRONMENT.md with
#    all values → CHANGE_ME), or BFG/filter-repo rewrite + force-push + GitHub "garbage collect".
#    Order: B and C before or concurrent with A, so the live token is not readable during the window.
```

---

## 6. Open items / not verifiable from here

1. **Populated reconciliation not yet exercised** — the pass in §4 is an empty-dataset round-trip. Re-run §4.1 once the two agents have ingested real rows; the first non-trivial count match is the real validation. *(Owner: ops, after first ingest wave.)*
2. **GitHub remote side unverifiable from this host** — repo visibility (public vs private), PAT scope, and whether the repo has forks/mirrors are server-side state. Item A/B/C in §5 must be executed against GitHub; the threat model should mark T-X3 "rotated + purged" only after B and C complete.
3. **`mkc_test` database exists** (not `mkc_restore_test`) — pre-existing, presumably the other agents' scratch DB. Not inspected per scope (no interference). Confirm ownership/cleanup in a later ops pass.
4. **`log_statement='ddl'` log volume** — unmeasured until ingest traffic is present; review `/var/log/postgresql/` size after the first week with logging on (§5 step 5).
5. **Peer-line blast radius** — the staged `local all mkc peer` line is inert until an OS user `mkc` is ever created; if that ever happens (e.g., a DB-backed service account), it becomes a passwordless path — in that case prefer dropping the line entirely and requiring TCP+SCRAM for `mkc`.
6. **Debian `pg_ctlcluster` manages these files** — any future `apt upgrade` of postgresql packages can reset `postgresql.conf`/`pg_hba.conf`; the §5 settings should be dropped into `conf.d/` (or the cluster config) so they survive package upgrades. *(Not applied — staged only.)*

---

*Produced by the DB audit agent (read/verify + one backup run). No live configuration changed; all hardening is staged in §5.*
