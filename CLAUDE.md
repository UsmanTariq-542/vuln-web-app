# CLAUDE.md

## Project Context

This is an **intentionally vulnerable web application** built for security education. It ships with 8 deliberate OWASP Top 10 vulnerabilities: SQL Injection, Stored XSS, Reflected XSS, Session Hijacking, Weak Password Storage, Exposed Database, No Rate Limiting, and CSRF. **All 8 are intentional and must not be "fixed" without an accompanying spec that says so.** This baseline is tagged `v0.1.0`.

Students are meant to: read the source, exploit each flaw, trace it to its root cause, and only then patch it as a separate learning exercise.

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
├── core/security.py           # MD5 password hashing (VULN-5)
├── db/session.py              # SQLite connection + init_db()
├── services/auth_service.py   # signup()/login() business logic (VULN-1)
└── api/routes/auth.py         # HTTP route handlers (VULN-2, VULN-3, VULN-6)

frontend/
├── templates/                 # login.html, signup.html, dashboard.html — read from disk per request, no caching
└── static/                    # css/styles.css, images/ (3 org logos)
```

## Vulnerability Map

| # | Vulnerability | File | Mechanism |
|---|---------------|------|-----------|
| 1 | SQL Injection | `backend/app/services/auth_service.py` | String concatenation in both `signup()`'s INSERT and `login()`'s SELECT |
| 2 | Stored XSS | `backend/app/api/routes/auth.py` | Unescaped `{{username}}` substitution in `/welcome` |
| 3 | Reflected XSS | `backend/app/api/routes/auth.py` | Unescaped `q` param (and result rows, and exception text) in `/search` |
| 4 | Session Hijacking | `backend/app/main.py` | Hardcoded `SECRET_KEY = "super-secret-key-12345"` |
| 5 | Weak Password Storage | `backend/app/core/security.py` | `hashlib.md5()`, no salt |
| 6 | Exposed Database | `backend/app/api/routes/auth.py` | `GET /download/db` — unauthenticated, serves the raw SQLite file |
| 7 | No Rate Limiting | *(absence)* | No throttling middleware registered anywhere in `main.py` |
| 8 | CSRF | *(absence)* | No CSRF token on any form, no validation on any POST route |

## Frontend-Backend Integration

- **Login**: `fetch()` POST → JSON response (`{"success": bool, "redirect"|"error": ...}`) → client-side redirect or inline error, no page reload.
- **Signup**: standard `<form>` POST → server-side redirect to `/login` on success, or an inline failure page on a duplicate username.
- **Dashboard**: server-side `str.replace('{{username}}', ...)` on a template string read fresh from disk on every request — no template engine, no escaping.

## Important Rules

- Never parameterize the SQL in `auth_service.py` or `auth.py`. String concatenation is the point (VULN-1).
- Never salt or replace the MD5 hashing in `security.py` (VULN-5).
- Never HTML-escape the `{{username}}` substitution in `/welcome` (VULN-2), or the `q` reflection / result rows / exception text in `/search` (VULN-3).
- Never source `SECRET_KEY` from an environment variable or a random generator (VULN-4) — it must stay the hardcoded literal.
- Never add authentication to `/download/db` (VULN-6).
- Never add rate-limiting middleware (VULN-7) or CSRF tokens/middleware (VULN-8).
- This application must never be deployed to production, exposed on the public internet, or connected to real user data. It is for isolated, localhost security education only.

## Specification Hierarchy

1. `docs/PRD.md` — Product requirements
2. `docs/TDD.md` — Technical design
3. `.claude/specs/app-foundation.md` — Foundation implementation specification
4. `.claude/specs/app-foundation-plan.md` — Foundation implementation plan

Prompts that generated each spec/plan/implementation live under `docs/prompts/`.
