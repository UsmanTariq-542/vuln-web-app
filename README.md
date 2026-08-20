# Vulnerable Web App — Security Education Lab

An intentionally vulnerable web application built for hands-on OWASP Top 10 security education. It shipped with 8 deliberate vulnerabilities across SQL Injection, XSS (stored + reflected), session hijacking, weak password storage, an exposed database, missing rate limiting, and CSRF — so students can find, exploit, and then remediate each one as a separate, spec-driven exercise.

**This application must never be deployed to production, exposed on the public internet, or connected to real user data. It is for isolated, localhost security education only.**

---

## Status

- **Baseline (`v0.1.0`):** all 8 vulnerabilities present and intentional.
- **Dark mode toggle:** a purely presentational light/dark theme switch has been added on top of the baseline (login, signup, dashboard). It does not touch any vulnerability.
- **VULN-5 (Weak Password Storage) — remediated (`v0.1.1`):** unsalted MD5 has been replaced with bcrypt (work factor ≥ 12) as a spec-driven remediation exercise.
- **VULN-1 (SQL Injection) — remediated (`v0.1.2`):** `signup()`'s `INSERT` and `login()`'s `SELECT` in `auth_service.py` now use parameterized queries (`?` placeholders + bound tuples) instead of string concatenation.
- **VULN-4 (Session Hijacking) — remediated:** the hardcoded `SECRET_KEY = "super-secret-key-12345"` literal in `main.py` has been replaced with a value sourced from the `SECRET_KEY` environment variable (falling back to an ephemeral `secrets.token_hex(32)` key with a startup warning if unset), and the `SessionMiddleware` registration now sets `https_only=True` and `max_age=1800` (30-minute session expiry, down from Starlette's 14-day default).
- **VULN-2 (Stored XSS) — remediated (`v0.1.4`):** `welcome_page()` in `auth.py` now passes the session's `username` through Python's standard-library `html.escape()` before substituting it into `dashboard.html`'s `{{username}}` placeholder, so a username stored as `<script>alert(1)</script>` (or any other markup/attribute-breakout payload) renders as inert, literal escaped text instead of executing.
- **VULN-6 (Exposed Database) — remediated:** `download_db()` in `auth.py` now requires an authenticated session — a request with no `user_id` in `request.session` is redirected to `/login` (302) instead of receiving the SQLite file. This app has no role/admin system, so the fix is "authenticated users only," not "admin only": any logged-in user (including one who just self-registered) can still download the full database, including other users' rows. This is a documented, intentional residual limitation — see `.claude/specs/exposed-database-fix.md`.
- **VULN-3 (Reflected XSS) — remediated:** `search_user()` in `auth.py` (`GET /search`) has been fixed for all three issues bundled into that route — the string-concatenated SQL query now uses `?` placeholders with a bound parameter tuple (same pattern as the VULN-1 fix), the `q` value and each result row's `username`/`email` are passed through `html.escape()` before being embedded in the response HTML, and the exception handler no longer leaks raw exception text, returning a fixed generic message instead. **All 8 original vulnerabilities are now remediated except VULN-7 (No Rate Limiting) and VULN-8 (CSRF)** — see [`CLAUDE.md`](./CLAUDE.md) for the current vulnerability map.

## Getting Started

```bash
# Install backend dependencies
cd backend && uv sync

# (Optional) set a stable session-signing key — see .env.example.
# If unset, the app generates a random ephemeral key at startup and
# warns on stderr; sessions are invalidated on every restart in that case.
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"

# Run the application (from project root)
uv run backend/app/main.py

# Access at http://localhost:3001
```

Accounts created before the bcrypt remediation (MD5-hashed passwords) can no longer log in — the app's SQLite file (`vulnerable_app.db`) should be deleted and recreated (happens automatically on next startup), or affected accounts re-registered via `/signup`.

Session cookies are now issued with `Secure` and expire after 30 minutes (`max_age=1800`) as part of the VULN-4 remediation. Any session cookie signed before this fix (or forged with the old hardcoded key) is rejected as unauthenticated.

## Architecture

Three-layer architecture: Presentation (HTML/CSS/JS) → Application (FastAPI) → Data (SQLite).

```
backend/app/
├── main.py                    # Entry point, session middleware (VULN-4 remediated), static mounts, DB init
├── core/security.py           # Password hashing: bcrypt, work factor 12 (VULN-5 remediated)
├── db/session.py              # SQLite connection + init_db()
├── services/auth_service.py   # signup()/login() business logic (VULN-1 remediated — parameterized queries)
└── api/routes/auth.py         # HTTP route handlers (VULN-2, VULN-3, VULN-6 remediated)

frontend/
├── templates/                 # login.html, signup.html, dashboard.html — read from disk per request, no caching
│                               # each includes a light/dark theme toggle in the shared header
└── static/                    # css/styles.css (CSS custom properties + dark theme overrides), images/
```

## Features

- **Signup / Login / Dashboard / Logout** — session-based auth flow (see [`CLAUDE.md`](./CLAUDE.md) for the exact request/response contract).
- **Dark mode toggle** — a header button on every page switches between light and dark themes via a `data-theme` attribute on `<html>`, driven entirely by CSS custom properties. The choice persists in the browser's `localStorage` and falls back to the OS's `prefers-color-scheme` when nothing is stored. No backend route, session field, or database column is involved — this is a client-only, additive UI feature.

## Vulnerability Map

| # | Vulnerability | Status | Location |
|---|---|---|---|
| 1 | SQL Injection | **Remediated** (parameterized queries) | `backend/app/services/auth_service.py` |
| 2 | Stored XSS | **Remediated** (`html.escape()` before `{{username}}` substitution, `v0.1.4`) | `backend/app/api/routes/auth.py` (`/welcome`) |
| 3 | Reflected XSS | **Remediated** (parameterized query + `html.escape()` on `q`/result rows + generic error message) | `backend/app/api/routes/auth.py` (`/search`) |
| 4 | Session Hijacking | **Remediated** (env-sourced `SECRET_KEY`, `https_only`, `max_age=1800`) | `backend/app/main.py` |
| 5 | Weak Password Storage | **Remediated** (bcrypt, work factor ≥ 12) | `backend/app/core/security.py` |
| 6 | Exposed Database | **Remediated** (session check on `GET /download/db`; authenticated-only, no role/admin tier) | `backend/app/api/routes/auth.py` |
| 7 | No Rate Limiting | Unfixed (intentional) | *(absence of throttling middleware)* |
| 8 | CSRF | Unfixed (intentional) | *(absence of CSRF tokens/middleware)* |

## Specifications

Every feature and remediation in this repo is spec-driven. See `.claude/specs/`:

- `app-foundation.md` / `app-foundation-plan.md` — the original vulnerable baseline.
- `dark-mode-toggle.md` / `dark-mode-toggle-plan.md` — the theme toggle feature.
- `bcrypt-password-hashing.md` / `bcrypt-password-hashing-plan.md` — the VULN-5 remediation.
- `sql-injection-fix.md` / `sql-injection-fix-plan.md` — the VULN-1 remediation.
- `session-hijacking-fix.md` / `session-hijacking-fix-plan.md` — the VULN-4 remediation.
- `stored-xss-fix.md` / `stored-xss-fix-plan.md` — the VULN-2 remediation.
- `exposed-database-fix.md` / `exposed-database-fix-plan.md` — the VULN-6 remediation.
- `reflected-xss-fix.md` / `reflected-xss-fix-plan.md` — the VULN-3 remediation.

Prompts that generated each spec/plan/implementation live under `docs/prompts/`.

See `docs/PRD.md` and `docs/TDD.md` for product requirements and technical design, and [`CLAUDE.md`](./CLAUDE.md) for the rules governing how this codebase may be changed.
