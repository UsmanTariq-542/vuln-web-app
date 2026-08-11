# CLAUDE.md

## Project Context

This is an **intentionally vulnerable web application** built for security education. It ships with 8 deliberate OWASP Top 10 vulnerabilities: SQL Injection, Stored XSS, Reflected XSS, Session Hijacking, Weak Password Storage, Exposed Database, No Rate Limiting, and CSRF. **All 8 are intentional and must not be "fixed" without an accompanying spec that says so.** This baseline is tagged `v0.1.0`.

Students are meant to: read the source, exploit each flaw, trace it to its root cause, and only then patch it as a separate learning exercise.

**Current state — two changes have been layered on top of the `v0.1.0` baseline, each via its own spec:**
- **Dark mode toggle** (`.claude/specs/dark-mode-toggle.md`): a purely presentational light/dark theme switch on the login, signup, and dashboard pages. Client-side only — no backend route, session field, or DB column added, and none of the 8 vulnerabilities were touched.
- **VULN-5 remediation** (`.claude/specs/bcrypt-password-hashing.md`): unsalted MD5 has been replaced with bcrypt (work factor ≥ 12). **This is the one vulnerability that has been intentionally fixed.** The other 7 remain unfixed and must still not be "fixed" without a new spec.

## Development Commands

```bash
# Install backend dependencies
cd backend && uv sync

# Run the application (from project root)
uv run backend/app/main.py

# Access at http://localhost:3001
```

## Architecture

Three-layer architecture: Presentation (HTML/CSS/JS) → Application (FastAPI) → Data (SQLite).

```
backend/app/
├── main.py                    # Entry point, session middleware, static mounts, DB init
├── core/security.py           # bcrypt password hashing, work factor 12 (VULN-5 — remediated)
├── db/session.py              # SQLite connection + init_db()
├── services/auth_service.py   # signup()/login() business logic (VULN-1)
└── api/routes/auth.py         # HTTP route handlers (VULN-2, VULN-3, VULN-6)

frontend/
├── templates/                 # login.html, signup.html, dashboard.html — read from disk per request, no caching
│                               # each carries a light/dark theme toggle in the shared header
└── static/                    # css/styles.css (theme variables + dark overrides), images/ (3 org logos)
```

## Vulnerability Map

| # | Vulnerability | Status | File | Mechanism |
|---|---------------|--------|------|-----------|
| 1 | SQL Injection | Unfixed (intentional) | `backend/app/services/auth_service.py` | String concatenation in both `signup()`'s INSERT and `login()`'s SELECT |
| 2 | Stored XSS | Unfixed (intentional) | `backend/app/api/routes/auth.py` | Unescaped `{{username}}` substitution in `/welcome` |
| 3 | Reflected XSS | Unfixed (intentional) | `backend/app/api/routes/auth.py` | Unescaped `q` param (and result rows, and exception text) in `/search` |
| 4 | Session Hijacking | Unfixed (intentional) | `backend/app/main.py` | Hardcoded `SECRET_KEY = "super-secret-key-12345"` |
| 5 | Weak Password Storage | **Remediated** | `backend/app/core/security.py` | `bcrypt.hashpw()`/`bcrypt.checkpw()`, work factor 12 — see `.claude/specs/bcrypt-password-hashing.md` |
| 6 | Exposed Database | Unfixed (intentional) | `backend/app/api/routes/auth.py` | `GET /download/db` — unauthenticated, serves the raw SQLite file |
| 7 | No Rate Limiting | Unfixed (intentional) | *(absence)* | No throttling middleware registered anywhere in `main.py` |
| 8 | CSRF | Unfixed (intentional) | *(absence)* | No CSRF token on any form, no validation on any POST route |

**VULN-5 remediation details:** `auth_service.login()` can no longer match the password hash inside the SQL `WHERE` clause (bcrypt salts are random per hash), so it now fetches the user row by `username` only and calls `verify_password()` in Python. The `SELECT`/`INSERT` queries themselves are still string-concatenated — VULN-1 was **not** incidentally fixed by this change. `verify_password()` wraps `bcrypt.checkpw()` in `try/except` so a legacy MD5 value left over from before the fix returns `False` (a normal `401`) instead of crashing. Accounts created before this change cannot log in and must re-register.

## Frontend-Backend Integration

- **Login**: `fetch()` POST → JSON response (`{"success": bool, "redirect"|"error": ...}`) → client-side redirect or inline error, no page reload.
- **Signup**: standard `<form>` POST → server-side redirect to `/login` on success, or an inline failure page on a duplicate username.
- **Dashboard**: server-side `str.replace('{{username}}', ...)` on a template string read fresh from disk on every request — no template engine, no escaping.
- **Theme toggle**: client-only, present on login, signup, and dashboard. A pre-render inline script in `<head>` reads `localStorage['theme']` (falling back to `prefers-color-scheme`) and sets `data-theme` on `<html>` before paint, to avoid a flash of the wrong theme. A header button toggles `data-theme` between `"light"`/`"dark"` and writes the choice back to `localStorage`. All theming is CSS custom-property overrides under `[data-theme="dark"]` in `styles.css` — no backend route, session field, or DB column is involved.

## Important Rules

- Never parameterize the SQL in `auth_service.py` or `auth.py`. String concatenation is the point (VULN-1).
- VULN-5 (weak password storage) has already been remediated with bcrypt per `.claude/specs/bcrypt-password-hashing.md` — never reintroduce MD5 or any other unsalted/fast hash in `security.py`, and never change `hash_password()`/`verify_password()` outside of what that spec describes without a new spec.
- Never HTML-escape the `{{username}}` substitution in `/welcome` (VULN-2), or the `q` reflection / result rows / exception text in `/search` (VULN-3).
- Never source `SECRET_KEY` from an environment variable or a random generator (VULN-4) — it must stay the hardcoded literal.
- Never add authentication to `/download/db` (VULN-6).
- Never add rate-limiting middleware (VULN-7) or CSRF tokens/middleware (VULN-8).
- The dark mode toggle is purely presentational (CSS + a small inline script) — never let changes to it touch `backend/app/**`, add a route, or add server-side state.
- This application must never be deployed to production, exposed on the public internet, or connected to real user data. It is for isolated, localhost security education only.

## Specification Hierarchy

1. `docs/PRD.md` — Product requirements
2. `docs/TDD.md` — Technical design
3. `.claude/specs/app-foundation.md` / `app-foundation-plan.md` — Foundation implementation spec/plan (the `v0.1.0` baseline, all 8 vulnerabilities intentional)
4. `.claude/specs/dark-mode-toggle.md` / `dark-mode-toggle-plan.md` — Light/dark theme toggle spec/plan
5. `.claude/specs/bcrypt-password-hashing.md` / `bcrypt-password-hashing-plan.md` — VULN-5 remediation spec/plan

Prompts that generated each spec/plan/implementation live under `docs/prompts/`.
