# Vulnerable Web App — Security Education Lab

An intentionally vulnerable web application built for hands-on OWASP Top 10 security education. It ships with 8 deliberate vulnerabilities across SQL Injection, XSS (stored + reflected), session hijacking, weak password storage, an exposed database, missing rate limiting, and CSRF — so students can find, exploit, and then remediate each one as a separate, spec-driven exercise.

**This application must never be deployed to production, exposed on the public internet, or connected to real user data. It is for isolated, localhost security education only.**

---

## Status

- **Baseline (`v0.1.0`):** all 8 vulnerabilities present and intentional.
- **Dark mode toggle:** a purely presentational light/dark theme switch has been added on top of the baseline (login, signup, dashboard). It does not touch any vulnerability.
- **VULN-5 (Weak Password Storage) — remediated (`v0.1.1`):** unsalted MD5 has been replaced with bcrypt (work factor ≥ 12) as a spec-driven remediation exercise.
- **VULN-1 (SQL Injection) — remediated (`v0.1.2`):** `signup()`'s `INSERT` and `login()`'s `SELECT` in `auth_service.py` now use parameterized queries (`?` placeholders + bound tuples) instead of string concatenation. **6 of the 8 original vulnerabilities remain intentionally unfixed** — see [`CLAUDE.md`](./CLAUDE.md) for the current vulnerability map.

## Getting Started

```bash
# Install backend dependencies
cd backend && uv sync

# Run the application (from project root)
uv run backend/app/main.py

# Access at http://localhost:3001
```

Accounts created before the bcrypt remediation (MD5-hashed passwords) can no longer log in — the app's SQLite file (`vulnerable_app.db`) should be deleted and recreated (happens automatically on next startup), or affected accounts re-registered via `/signup`.

## Architecture

Three-layer architecture: Presentation (HTML/CSS/JS) → Application (FastAPI) → Data (SQLite).

```
backend/app/
├── main.py                    # Entry point, session middleware, static mounts, DB init
├── core/security.py           # Password hashing: bcrypt, work factor 12 (VULN-5 remediated)
├── db/session.py              # SQLite connection + init_db()
├── services/auth_service.py   # signup()/login() business logic (VULN-1 remediated — parameterized queries)
└── api/routes/auth.py         # HTTP route handlers (VULN-2, VULN-3, VULN-6 — unremediated)

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
| 2 | Stored XSS | Unfixed (intentional) | `backend/app/api/routes/auth.py` (`/welcome`) |
| 3 | Reflected XSS | Unfixed (intentional) | `backend/app/api/routes/auth.py` (`/search`) |
| 4 | Session Hijacking | Unfixed (intentional) | `backend/app/main.py` (hardcoded `SECRET_KEY`) |
| 5 | Weak Password Storage | **Remediated** (bcrypt, work factor ≥ 12) | `backend/app/core/security.py` |
| 6 | Exposed Database | Unfixed (intentional) | `backend/app/api/routes/auth.py` (`GET /download/db`) |
| 7 | No Rate Limiting | Unfixed (intentional) | *(absence of throttling middleware)* |
| 8 | CSRF | Unfixed (intentional) | *(absence of CSRF tokens/middleware)* |

## Specifications

Every feature and remediation in this repo is spec-driven. See `.claude/specs/`:

- `app-foundation.md` / `app-foundation-plan.md` — the original vulnerable baseline.
- `dark-mode-toggle.md` / `dark-mode-toggle-plan.md` — the theme toggle feature.
- `bcrypt-password-hashing.md` / `bcrypt-password-hashing-plan.md` — the VULN-5 remediation.
- `sql-injection-fix.md` / `sql-injection-fix-plan.md` — the VULN-1 remediation.

Prompts that generated each spec/plan/implementation live under `docs/prompts/`.

See `docs/PRD.md` and `docs/TDD.md` for product requirements and technical design, and [`CLAUDE.md`](./CLAUDE.md) for the rules governing how this codebase may be changed.
