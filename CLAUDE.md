# CLAUDE.md

## Project Context

This is an **intentionally vulnerable web application** built for security education. It ships with 8 deliberate OWASP Top 10 vulnerabilities: SQL Injection, Stored XSS, Reflected XSS, Session Hijacking, Weak Password Storage, Exposed Database, No Rate Limiting, and CSRF. **All 8 are intentional and must not be "fixed" without an accompanying spec that says so.** This baseline is tagged `v0.1.0`.

Students are meant to: read the source, exploit each flaw, trace it to its root cause, and only then patch it as a separate learning exercise.

**Current state — three changes have been layered on top of the `v0.1.0` baseline, each via its own spec:**
- **Dark mode toggle** (`.claude/specs/dark-mode-toggle.md`): a purely presentational light/dark theme switch on the login, signup, and dashboard pages. Client-side only — no backend route, session field, or DB column added, and none of the 8 vulnerabilities were touched.
- **VULN-5 remediation** (`.claude/specs/bcrypt-password-hashing.md`, `v0.1.1`): unsalted MD5 has been replaced with bcrypt (work factor ≥ 12).
- **VULN-1 remediation** (`.claude/specs/sql-injection-fix.md` / `sql-injection-fix-plan.md`, `v0.1.2`): `signup()`'s `INSERT` and `login()`'s `SELECT` in `auth_service.py` now use parameterized queries (`?` placeholders with bound tuples) instead of string concatenation.
- **VULN-4 remediation** (`.claude/specs/session-hijacking-fix.md` / `session-hijacking-fix-plan.md`): the hardcoded `SECRET_KEY` literal in `main.py` has been replaced with a value sourced from the `SECRET_KEY` environment variable (falling back to an ephemeral `secrets.token_hex(32)` key with a startup warning if unset), and the `SessionMiddleware` registration now sets `https_only=True` and `max_age=1800`.
- **VULN-2 remediation** (`.claude/specs/stored-xss-fix.md` / `stored-xss-fix-plan.md`, `v0.1.4`): `welcome_page()` in `auth.py` now passes `request.session["username"]` through Python's standard-library `html.escape()` before substituting it into `dashboard.html`'s `{{username}}` placeholder, so a stored `<script>`/`<img onerror>` payload renders as inert escaped text instead of executing.
- **VULN-6 remediation** (`.claude/specs/exposed-database-fix.md` / `exposed-database-fix-plan.md`): `download_db()` in `auth.py` now requires `request: Request` and checks `"user_id" not in request.session` before serving the file — mirroring `welcome_page()`'s existing check — redirecting unauthenticated requests to `/login` (302) instead of returning the SQLite file. The app has no role/admin system, so this closes only the "fully public, zero-authentication" form of VULN-6: any authenticated user (including a freshly self-registered one) can still download the entire database, including other users' rows. This residual gap is intentional and documented, not a defect. **VULN-5, VULN-1, VULN-4, VULN-2, and VULN-6 are the five vulnerabilities that have been intentionally fixed.** The other 3 (VULN-3, VULN-7, VULN-8) remain unfixed and must still not be "fixed" without a new spec.

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
├── main.py                    # Entry point, session middleware, static mounts, DB init (VULN-4 — remediated)
├── core/security.py           # bcrypt password hashing, work factor 12 (VULN-5 — remediated)
├── db/session.py              # SQLite connection + init_db()
├── services/auth_service.py   # signup()/login() business logic (VULN-1 — remediated)
└── api/routes/auth.py         # HTTP route handlers (VULN-2, VULN-6 — remediated; VULN-3 unfixed)

frontend/
├── templates/                 # login.html, signup.html, dashboard.html — read from disk per request, no caching
│                               # each carries a light/dark theme toggle in the shared header
└── static/                    # css/styles.css (theme variables + dark overrides), images/ (3 org logos)
```

## Vulnerability Map

| # | Vulnerability | Status | File | Mechanism |
|---|---------------|--------|------|-----------|
| 1 | SQL Injection | **Remediated** | `backend/app/services/auth_service.py` | Parameterized (`?`-placeholder) queries in both `signup()`'s INSERT and `login()`'s SELECT — see `.claude/specs/sql-injection-fix.md` |
| 2 | Stored XSS | **Remediated** | `backend/app/api/routes/auth.py` | `html.escape()` applied to the session username before `{{username}}` substitution in `/welcome` — see `.claude/specs/stored-xss-fix.md` |
| 3 | Reflected XSS | Unfixed (intentional) | `backend/app/api/routes/auth.py` | Unescaped `q` param (and result rows, and exception text) in `/search` |
| 4 | Session Hijacking | **Remediated** | `backend/app/main.py` | `SECRET_KEY` sourced from the `SECRET_KEY` env var (ephemeral random fallback if unset); `SessionMiddleware` hardened with `https_only=True`, `max_age=1800` — see `.claude/specs/session-hijacking-fix.md` |
| 5 | Weak Password Storage | **Remediated** | `backend/app/core/security.py` | `bcrypt.hashpw()`/`bcrypt.checkpw()`, work factor 12 — see `.claude/specs/bcrypt-password-hashing.md` |
| 6 | Exposed Database | **Remediated** | `backend/app/api/routes/auth.py` | `GET /download/db` now requires an authenticated session (mirrors `/welcome`'s check); no role/admin tier exists, so any authenticated user can still download the file — see `.claude/specs/exposed-database-fix.md` |
| 7 | No Rate Limiting | Unfixed (intentional) | *(absence)* | No throttling middleware registered anywhere in `main.py` |
| 8 | CSRF | Unfixed (intentional) | *(absence)* | No CSRF token on any form, no validation on any POST route |

**VULN-5 remediation details:** `auth_service.login()` can no longer match the password hash inside the SQL `WHERE` clause (bcrypt salts are random per hash), so it now fetches the user row by `username` only and calls `verify_password()` in Python. `verify_password()` wraps `bcrypt.checkpw()` in `try/except` so a legacy MD5 value left over from before the fix returns `False` (a normal `401`) instead of crashing. Accounts created before this change cannot log in and must re-register.

**VULN-1 remediation details:** `auth_service.signup()`'s `INSERT` and `login()`'s `SELECT` now use `?` placeholders with values passed as a bound parameter tuple to `conn.execute()`, instead of string concatenation. `login()`'s control flow is otherwise unchanged: it still fetches the row by `username` only and calls `verify_password()` in Python (per the VULN-5 remediation above). See `.claude/specs/sql-injection-fix.md`.

**VULN-4 remediation details:** `main.py` no longer defines `SECRET_KEY` as a hardcoded literal. It is read via `os.environ.get("SECRET_KEY")`; if unset, it falls back to a randomly generated ephemeral key (`secrets.token_hex(32)`) and prints a startup warning to stderr — the app still runs out of the box, but every session is invalidated on restart in that fallback mode. The `app.add_middleware(SessionMiddleware, ...)` call also now sets `https_only=True` (cookie marked `Secure`) and `max_age=1800` (30-minute expiry, replacing Starlette's 14-day default). No session-store architecture change: sessions remain stateless, `itsdangerous`-signed cookies — only the signing key and cookie parameters changed. `auth_service.login()`'s session writes and `auth.py`'s `welcome_page()`/`logout()` session reads/clears are untouched. See `.claude/specs/session-hijacking-fix.md`.

**VULN-2 remediation details:** `auth.py`'s `welcome_page()` now imports the standard-library `html` module and calls `html.escape()` on `request.session["username"]` before substituting it into `dashboard.html`'s `{{username}}` placeholder via the existing `str.replace()` mechanism. `dashboard.html` itself, the per-request disk read (no caching), and the plain string-substitution mechanism are all unchanged — only the substituted value is escaped. A username stored as `<script>alert(1)</script>` now renders as literal escaped text in the browser instead of executing. See `.claude/specs/stored-xss-fix.md`.

**VULN-6 remediation details:** `auth.py`'s `download_db()` gained a `request: Request` parameter and, as its first statement, `if "user_id" not in request.session: return RedirectResponse(url="/login", status_code=302)` — textually identical in form to the check already used in `welcome_page()`. `Request` and `RedirectResponse` were already imported in the file, so no new imports were added. The authenticated path is otherwise byte-for-byte unchanged: `FileResponse(DB_PATH, filename="vulnerable_app.db")` is still returned exactly as before. No route other than `download_db()` was touched, and no role/permission/admin concept was introduced — the app still has only session-presence auth. Any authenticated user (including one who just self-registered via the public `/signup`) can still download the full database, including every other user's row; this is a documented, intentional residual limitation, not a defect. See `.claude/specs/exposed-database-fix.md`.

## Frontend-Backend Integration

- **Login**: `fetch()` POST → JSON response (`{"success": bool, "redirect"|"error": ...}`) → client-side redirect or inline error, no page reload.
- **Signup**: standard `<form>` POST → server-side redirect to `/login` on success, or an inline failure page on a duplicate username.
- **Dashboard**: server-side `str.replace('{{username}}', ...)` on a template string read fresh from disk on every request — no template engine; the substituted username is now HTML-escaped via `html.escape()` (VULN-2 remediation).
- **Theme toggle**: client-only, present on login, signup, and dashboard. A pre-render inline script in `<head>` reads `localStorage['theme']` (falling back to `prefers-color-scheme`) and sets `data-theme` on `<html>` before paint, to avoid a flash of the wrong theme. A header button toggles `data-theme` between `"light"`/`"dark"` and writes the choice back to `localStorage`. All theming is CSS custom-property overrides under `[data-theme="dark"]` in `styles.css` — no backend route, session field, or DB column is involved.

## Important Rules

- VULN-1 (SQL injection in `auth_service.py`) has already been remediated with parameterized queries per `.claude/specs/sql-injection-fix.md` — never reintroduce string-concatenated SQL in `signup()`/`login()`, and never change their query construction outside of what that spec describes without a new spec.
- Never parameterize the SQL in `auth.py` (the `/search` route). String concatenation is the point (VULN-3).
- VULN-5 (weak password storage) has already been remediated with bcrypt per `.claude/specs/bcrypt-password-hashing.md` — never reintroduce MD5 or any other unsalted/fast hash in `security.py`, and never change `hash_password()`/`verify_password()` outside of what that spec describes without a new spec.
- VULN-2 (stored XSS in `/welcome`) has already been remediated with `html.escape()` per `.claude/specs/stored-xss-fix.md` — never reintroduce unescaped substitution of the session username into `{{username}}`, and never change this outside of what that spec describes without a new spec.
- Never escape the `q` reflection / result rows / exception text in `/search` (VULN-3) — string concatenation and unescaped output there are the point.
- VULN-4 (session hijacking) has already been remediated per `.claude/specs/session-hijacking-fix.md` — `SECRET_KEY` is sourced from the `SECRET_KEY` environment variable (with an ephemeral random fallback), and `SessionMiddleware` sets `https_only=True`/`max_age=1800`; never reintroduce the hardcoded `"super-secret-key-12345"` literal, and never change this configuration outside of what that spec describes without a new spec.
- VULN-6 (exposed database) has already been remediated with a session-presence check per `.claude/specs/exposed-database-fix.md` — never remove the `"user_id" not in request.session` check from `download_db()`, and never change it outside of what that spec describes without a new spec. Do not add a role/admin system to further restrict it without a new spec — the current fix is intentionally "authenticated users only."
- Never add rate-limiting middleware (VULN-7) or CSRF tokens/middleware (VULN-8).
- The dark mode toggle is purely presentational (CSS + a small inline script) — never let changes to it touch `backend/app/**`, add a route, or add server-side state.
- This application must never be deployed to production, exposed on the public internet, or connected to real user data. It is for isolated, localhost security education only.

## Specification Hierarchy

1. `docs/PRD.md` — Product requirements
2. `docs/TDD.md` — Technical design
3. `.claude/specs/app-foundation.md` / `app-foundation-plan.md` — Foundation implementation spec/plan (the `v0.1.0` baseline, all 8 vulnerabilities intentional)
4. `.claude/specs/dark-mode-toggle.md` / `dark-mode-toggle-plan.md` — Light/dark theme toggle spec/plan
5. `.claude/specs/bcrypt-password-hashing.md` / `bcrypt-password-hashing-plan.md` — VULN-5 remediation spec/plan
6. `.claude/specs/sql-injection-fix.md` / `sql-injection-fix-plan.md` — VULN-1 remediation spec/plan
7. `.claude/specs/session-hijacking-fix.md` / `session-hijacking-fix-plan.md` — VULN-4 remediation spec/plan
8. `.claude/specs/stored-xss-fix.md` / `stored-xss-fix-plan.md` — VULN-2 remediation spec/plan
9. `.claude/specs/exposed-database-fix.md` / `exposed-database-fix-plan.md` — VULN-6 remediation spec/plan

Prompts that generated each spec/plan/implementation live under `docs/prompts/`.
