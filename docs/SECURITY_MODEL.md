# MKC Security Model

> **Status: skeleton (documentation foundation wave).** The section structure is final; body content is written in Wave 5 (security) after the auth hardening, rate limiting, and input-validation sweep, and validated against the running code.

## 1. Threat Model

The assets to protect (the `mkc` PostgreSQL database, the `MKC_API_TOKEN` secret, the gitignored source corpora under `repos/` and `content-archive/`, and the host itself), the trust boundaries (local-network operator, API client, ingested repo content treated as untrusted data, AI agents as first-class consumers), and the assumed adversaries (accidental local operator error, a compromised client token, malicious content *inside* an ingested repo). The filled-in section will include a STRIDE-style analysis per boundary and the controls mapped to each threat.

## 2. Authentication and Authorization

The bearer-token model in full: token format and generation (`openssl rand -hex 20`, 40+ chars), where it is stored (`.env`, gitignored — the committed template is `.env.example` with `CHANGE_ME`), how it is verified in the request path, which endpoints are unauthenticated by default (`/healthz`, `/metrics`, `/api/v1/status`) and why that surface is safe to expose, token rotation procedure, and the 401-only failure behavior (never 403/500 on auth failure). Wave 5 will add the rate-limiting design (60 req/min per client, 429 + `Retry-After`) and its configuration knobs.

## 3. Data Handling and Input Validation

How untrusted input is handled end-to-end: Pydantic schema validation on every request body (invalid enums → 422, never 500), path-parameter validation before DB access, the no-secrets-in-code policy (tokens/DB passwords from environment only; log redaction of token and password fields; the `.gitignore` entries that keep `.env`, `repos/`, and `content-archive/` out of git), and the treatment of ingested repo content as data — extraction reads bytes and text, never executes anything from the corpus.

## 4. Provenance Integrity

Why provenance is a security control: immutable provenance fields (API rejects mutation with 422) prevent a compromised caller from re-pointing knowledge at fabricated sources; `commit_hash` pinning makes tampering detectable (broken `file_path` + `commit_hash` links surface as health warnings, never silent drops); and the append-only insight/decision history means an attacker cannot erase a rejected experiment or a superseded decision. Wave 5 will document the audit log (who/what/when/evidence for every transition) and the controls around report generation.

## 5. Secrets and Key Management

The secret inventory (PostgreSQL password, `MKC_API_TOKEN`, any future embedding/LLM API keys), where each lives (`.env` only), the rotation runbook per secret, the no-secrets-in-docs rule (all examples use `CHANGE_ME`), and the secret-scanning control that lands with the CI pipeline in Wave 4/5 (scan of committed files, log output, and generated reports).
