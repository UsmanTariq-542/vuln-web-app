# App Foundation — Implementation Plan

## Vulnerable Web Application (Security Education Lab)

**Version:** 1.0.0
**Source Documents:** `docs/PRD.md`, `docs/TDD.md`, `.claude/specs/app-foundation.md`
**Target Release:** v0.1.0 (fully vulnerable baseline)

---

## ⚠️ Read This Before Implementing Anything

This plan builds an **intentionally vulnerable** application for classroom security education (see `docs/PRD.md` §6 and `docs/TDD.md` §5). Every one of the 8 flaws below is **deliberate and required**. The application is a teaching artifact: students exploit these flaws, trace them to their root cause in the source, and then remediate them.

**The single most important instruction in this plan:**

> All SQL in `auth_service.py` and `auth.py` **must** be built with **string concatenation**. Do **not** use parameterized queries, prepared statements, or an ORM. Do **not** HTML-escape reflected output. Do **not** substitute bcrypt/argon2 for MD5. Do **not** add authentication to `/download/db`. Do **not** add rate-limiting or CSRF middleware.

A well-intentioned implementer's instinct will be to "fix" these as they write them. Doing so **breaks the educational purpose of the project** and produces an app that fails every acceptance test in Phase 10. If a security linter or code-review agent flags these, the correct response is to leave them in place — they are the product.

**Non-negotiable safety boundaries** (from PRD §6.2, TDD §5.2): this app must never be deployed to production, exposed on the public internet, or connected to real user data. It runs on `localhost` in an isolated lab environment only.

---

## Vulnerability Map

Each flaw traces to exactly one phase and file. Use this table to verify completeness at the end.

| # | Vulnerability | Phase | File | Mechanism |
|---|---|---|---|---|
| 1 | SQL Injection | 4 | `services/auth_service.py` | String-concatenated `INSERT` (signup) and `SELECT` (login) |
| 2 | Stored XSS | 5 | `api/routes/auth.py` | `html.replace('{{username}}', username)` — no escaping |
| 3 | Reflected XSS | 5 | `api/routes/auth.py` | `q` param interpolated into `/search` HTML unescaped |
| 4 | Session Hijacking | 6 | `main.py` | Hardcoded `SECRET_KEY = "super-secret-key-12345"` |
| 5 | Weak Password Storage | 3 | `core/security.py` | `hashlib.md5`, no salt, no KDF |
| 6 | Exposed Database | 5 | `api/routes/auth.py` | `GET /download/db` with no auth check |
| 7 | No Rate Limiting | 6 | `main.py` (by omission) | No throttling middleware registered |
| 8 | CSRF | 7 (by omission) | templates | No CSRF token on any form; no validation on any POST |

Note that **#7 and #8 are vulnerabilities of omission** — there is no code to write for them. They exist because the middleware stack in Phase 6 and the forms in Phase 7 deliberately lack these protections. Do not add them.

---

## Phase 1: Project Structure

### Files/directories to create

**Backend package** (11 files):

```
backend/app/main.py
backend/app/__init__.py                    (empty)
backend/app/core/__init__.py               (empty)
backend/app/core/security.py
backend/app/db/__init__.py                 (empty)
backend/app/db/session.py
backend/app/services/__init__.py           (empty)
backend/app/services/auth_service.py
backend/app/api/__init__.py                (empty)
backend/app/api/routes/__init__.py         (empty)
backend/app/api/routes/auth.py
```

The five `__init__.py` files must exist and be **empty** — they exist solely to make `app`, `app.core`, `app.db`, `app.services`, `app.api`, and `app.api.routes` importable packages. Note `backend/app/api/routes/` needs `__init__.py` at *both* the `api/` and `api/routes/` levels.

**Backend package manifest**: `backend/pyproject.toml`

- Build system: **hatchling**
- Dependencies:
  - `fastapi>=0.109.0`
  - `uvicorn>=0.27.0`
  - `python-multipart>=0.0.6` (required for FastAPI's `Form(...)` parsing)
  - `itsdangerous>=2.0.0` (required by Starlette's `SessionMiddleware` for cookie signing)
- Optional dev dependency group containing `pytest`

**Frontend directories:**

```
frontend/templates/          → login.html, signup.html, dashboard.html (Phase 7)
frontend/static/css/         → styles.css (Phase 8)
frontend/static/images/      → already present, do not modify
```

`frontend/static/images/` already contains `PUCIT_Logo.png`, `blue-logo-scl2.png`, and `excaliat-logo.png`. Leave these untouched — Phase 7 references them by name.

### Notes on the dual `pyproject.toml`

A root-level `pyproject.toml` already exists (created by `uv init`, with dependencies already resolved into `uv.lock`). Phase 1 adds a **second** manifest at `backend/pyproject.toml`. Both are intended: the root one makes `uv run backend/app/main.py` work from the project root, while `backend/pyproject.toml` describes the backend as a self-contained installable package (matching `docs/TDD.md` §6.5 and §11.2).

The version floors above are **minimums** from `docs/TDD.md` §10.1. The versions already installed in the root environment sit well above them (fastapi 0.141.x, uvicorn 0.52.x, python-multipart 0.0.32, itsdangerous 2.2.x). This is compatible — do not pin downward to match the floors exactly.

---

## Phase 2: Database Layer

### File: `backend/app/db/session.py`

**`get_db()`**
- Opens a `sqlite3` connection to `vulnerable_app.db` located at the **project root** (not inside `backend/`). Resolve this path relative to the file's own location so it is stable regardless of the current working directory.
- Pass `check_same_thread=False` — FastAPI serves requests across threads, and this flag lets a single connection object be shared. (Simplification appropriate for a teaching lab; not a production pattern.)
- Set `conn.row_factory = sqlite3.Row` so query results support both index and column-name access (`row["username"]`).
- Returns the connection.

**`init_db()`**
- Calls `get_db()`, then executes:

```sql
CREATE TABLE IF NOT EXISTS users (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    email    TEXT,
    password TEXT
)
```

- `CREATE TABLE IF NOT EXISTS` is what satisfies two spec requirements simultaneously: a missing DB file is recreated automatically, **and** existing data survives a restart untouched (spec §2, EC-07, EC-08, AC-06). Never issue a `DROP TABLE` or a destructive reset here.
- The `UNIQUE` constraint on `username` is the **sole** duplicate-account defense (spec §13, rule 6). Phase 4 relies on catching the resulting `IntegrityError` rather than doing a pre-check `SELECT`.
- Commits and closes.

---

## Phase 3: Security Utilities

### File: `backend/app/core/security.py`

Two functions, both built on `hashlib.md5` with **no salt** — this is **VULN-5, intentional**:

**`hash_password(password: str) -> str`**
- Encodes the password to bytes and returns `hashlib.md5(...).hexdigest()`.
- No salt, no pepper, no key-derivation function, no iteration count. MD5 is cryptographically broken and unsalted digests are trivially reversible via rainbow tables — which is precisely the lesson (`docs/PRD.md` VULN-5, `docs/TDD.md` §4.3).

**`verify_password(plain: str, hashed: str) -> bool`**
- Hashes `plain` via `hash_password()` and compares the result to `hashed`, returning the boolean.
- A plain `==` comparison is fine here; do not reach for `secrets.compare_digest`. (Constant-time comparison is a *fix*, and this baseline ships unfixed.)

> Do **not** substitute bcrypt, argon2, scrypt, or PBKDF2. Do **not** add a salt column. The remediation to bcrypt is a *later* exercise for the student, not part of this baseline.

---

## Phase 4: Business Logic

### File: `backend/app/services/auth_service.py`

This file contains **VULN-1 (SQL Injection)** in both functions. Both queries are assembled by **string concatenation of user-controlled input**. This is the single most important requirement in this phase.

### `signup(username, email, password)`

1. Receives the three values (passed through from FastAPI `Form(...)` params in the route layer).
2. Validates all three fields are present/non-empty; returns a failure response if any are missing.
3. Hashes the password via `hash_password()` (MD5, per Phase 3).
4. **Builds the INSERT by string concatenation — VULN-1:**

```python
query = "INSERT INTO users (username, email, password) VALUES ('" + username + "', '" + email + "', '" + hashed + "')"
```

   No `?` placeholders. No parameter tuple. The username and email flow directly into SQL syntax.
5. Executes the query and commits.
6. **On success**: returns a `RedirectResponse` to `/login` with status code **302** (spec SP-01, AC-01).
7. **On failure**: catches the `sqlite3.IntegrityError` raised by the `UNIQUE` constraint on `username` and returns a response carrying the message **"Username already exists"** (spec AP-01, EC-01, TC-02). The constraint — not a pre-check query — is what detects the duplicate.

### `login(request, username, password)`

1. Receives the `Request` object plus the two form values.
2. Validates both fields are present; returns a failure response if either is missing (spec EC-03, TC-07).
3. Hashes the submitted password via `hash_password()`.
4. **Builds the SELECT by string concatenation — VULN-1:**

```python
query = "SELECT * FROM users WHERE username = '" + username + "' AND password = '" + hashed + "'"
```

   Note this design detail: the password hash is matched **inside the SQL query**, not verified in Python afterward. That is what makes the classic `' OR '1'='1' --` payload bypass the password check entirely (`docs/TDD.md` §7.1) — the comment marker truncates the `AND password = ...` clause. Keeping the hash comparison in SQL is therefore **required** for the intended exploit to work.
5. Executes the query and fetches one row.
6. **On match** — establish the session and return JSON:
   - Write all three session keys **together**: `request.session["user_id"]`, `request.session["username"]`, `request.session["email"]` (spec §8 — never partially populated).
   - Return a `JSONResponse` with body `{"success": true, "redirect": "/welcome"}`.
   - JSON (not a redirect) because the login form submits via `fetch()`; the frontend JS reads `data.redirect` and navigates with `window.location.href` (spec §3.2, §13 rule 4).
7. **On no match** — return a `JSONResponse` with HTTP status **401** and an error message in the body, and **do not** create a session. The frontend renders `data.error` inline without reloading the page (spec AP-02, TC-06).

> The asymmetry is deliberate and specified: **signup responds with a redirect, login responds with JSON** (spec §13, business rule 4). Do not unify them.

---

## Phase 5: Route Handlers

### File: `backend/app/api/routes/auth.py`

All nine routes are registered on a **single `APIRouter`** instance, which Phase 6 includes into the FastAPI app.

Templates are read from disk **on every request** (`open(...).read()`), never cached at import time. This is a specified behavior, not an oversight — it means a template edit is visible on the next request with no restart (spec §2, §13 rule 5, TC-14).

| Route | Behavior |
|---|---|
| `GET /` | `RedirectResponse` to `/signup`, status **302** |
| `GET /signup` | Read `frontend/templates/signup.html` from disk → `HTMLResponse` |
| `POST /signup` | Accept `username`, `email`, `password` via `Form(...)`; delegate to `auth_service.signup()` |
| `GET /login` | Read `frontend/templates/login.html` from disk → `HTMLResponse` |
| `POST /login` | Accept `username`, `password` via `Form(...)`; delegate to `auth_service.login()`, passing the `Request` object through so the service can write the session |
| `GET /download/db` | **VULN-6** — see below |
| `GET /search?q=` | **VULN-3** — see below |
| `GET /welcome` | **VULN-2** — see below |
| `GET /logout` | `request.session.clear()`, then `RedirectResponse` to `/login` |

### `GET /download/db` — VULN-6 (Exposed Database), intentional

- Returns a `FileResponse` serving the `vulnerable_app.db` file directly.
- **No session check. No authentication. No authorization. No role check.** Anyone who knows the URL downloads the entire user table — every username, email, and MD5 hash (`docs/TDD.md` §7.1).
- Do not add an auth guard "just to be safe." The absence of the guard *is* the lesson, and it chains directly into VULN-5: download the DB, then crack the unsalted MD5 hashes offline.

### `GET /search?q=` — VULN-3 (Reflected XSS), intentional

Three separate flaws live in this one handler:

1. **SQL by string concatenation** with a `LIKE` wildcard match against both `username` and `email`:

```python
query = "SELECT username, email FROM users WHERE username LIKE '%" + q + "%' OR email LIKE '%" + q + "%'"
```

2. **The `q` parameter is interpolated directly into the returned HTML with no escaping** — this is VULN-3 proper. Result rows are likewise emitted raw (e.g. `f"<li>{row[0]} ({row[1]})</li>"`), so stored payloads render too.
3. **On exception**, the handler returns an error string containing `str(e)` — leaking raw SQLite error text (table names, SQL fragments) to the caller. This is deliberate information leakage that assists the student's SQLi exploration.

- The query parameter is **required**; a request with no `q` performs no match and returns no rows (spec §7, AP-04, TC-13).
- Returns `HTMLResponse`.

### `GET /welcome` — VULN-2 (Stored XSS), intentional

1. Check `'user_id' in request.session`. If absent, `RedirectResponse` to `/login` — no dashboard content is rendered (spec FR-03, AP-03, TC-09). Session presence is the **only** authorization signal; do not re-query the database to confirm the user still exists (spec §13 rule 1).
2. Read `frontend/templates/dashboard.html` from disk.
3. **Substitute the username with no escaping — VULN-2:**

```python
html = html.replace('{{username}}', request.session['username'])
```

   A username registered as `<img src=x onerror=alert('XSS')>` was stored raw by Phase 4 and is now emitted raw into the DOM, executing on every page load. Do **not** call `html.escape()` here — that is the remediation exercise, not the baseline.
4. Return `HTMLResponse`.

> Naming note: `html` is used above as a local variable for the template string. If the stdlib `html` module is ever imported into this file, rename the local to avoid shadowing — but do not import it for escaping purposes.

### `GET /logout`

- `request.session.clear()` — clears **all** session keys together, not selectively (spec §8).
- `RedirectResponse` to `/login`.
- After this, a subsequent `/welcome` request must redirect to login (spec SP-04, TC-10).

---

## Phase 6: Application Entry Point

### File: `backend/app/main.py`

**1. `sys.path` bootstrap — must be the very first thing in the file**

Before any `from app...` import, insert the `backend/` directory into `sys.path`, resolved relative to `__file__`. This makes the `app` package importable regardless of launch directory, so **both** of these work:

```bash
uv run backend/app/main.py     # from project root
python app/main.py             # from backend/
```

This must precede the application imports or they will fail with `ModuleNotFoundError: No module named 'app'`.

**2. FastAPI app + middleware**

- Instantiate the FastAPI app.
- Register `SessionMiddleware` with a **hardcoded** secret — **VULN-4, intentional**:

```python
SECRET_KEY = "super-secret-key-12345"
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
```

  A constant, guessable, source-committed key means anyone reading the repo can forge or tamper with a signed session cookie. Do **not** read this from an environment variable, do **not** generate it with `secrets.token_hex()`, and do **not** move it to a `.env` file — all three are the *remediation*, which is a later exercise.

**3. Router**

- Include the `APIRouter` from Phase 5.

**4. Static mounts**

- `/static/css` → `frontend/static/css`
- `/static/images` → `frontend/static/images`

Resolve both paths relative to the file location so they work from any working directory. Assets must be reachable as soon as the server is listening, with no build step (spec §2).

**5. Database init**

- Call `init_db()` at **module level** (import time), so the schema exists before the first request.

**6. Server**

- Run uvicorn on host `0.0.0.0`, port **3001**, with the port overridable via a `PORT` environment variable.

**7. VULN-7 (No Rate Limiting) — by omission, intentional**

Register **no** throttling middleware, no per-IP counter, no `slowapi`, no lockout. Unlimited login attempts must be possible so students can run a brute-force script against `/login` and observe zero resistance (`docs/PRD.md` VULN-7). There is no code to write here — the vulnerability is the empty space where a limiter would go.

---

## Phase 8 dependency note

Phases 7 and 8 together implement §5 of `.claude/specs/app-foundation.md` (the Complete Visual Design Specification). That section is the authoritative source for every color, size, weight, radius, and shadow value. **Read spec §5 before writing any markup or CSS** — the values below are summarized for orientation, but the spec governs.

---

## Phase 7: Frontend Templates

### Directory: `frontend/templates/`

**Shared across all three pages** — a fixed header, 70px tall, white background with a bottom border and the header shadow (`0 2px 10px rgba(26,35,126,0.08)`): app title anchored left, the three organizational logos (54×54px each) anchored right, referencing the existing files in `frontend/static/images/`.

**VULN-8 (CSRF) — by omission, intentional:** none of the forms below carry a CSRF token, and no POST handler validates one. Do not add a hidden token field, a double-submit cookie, a `SameSite` attribute change, or an `Origin`/`Referer` check. An attacker-hosted form must be able to POST to `/signup` or `/login` and have it succeed (`docs/TDD.md` §7.1).

### `login.html`

- **Layout**: two-column 50/50 split-screen.
  - **Left panel**: deep blue gradient `#0d1b5e → #1a237e → #283593`, carrying a badge label, welcome heading, description, and a bullet list of Security Lab content. Decorative semi-transparent white circles at ~7% opacity overlay the gradient.
  - **Right panel**: white, containing a centered form of max-width 400px — title, subtitle, username field, password field, an error-message area, a full-width login button (`#1a237e` background, white text), and a link to the signup page.
- **Submission — `fetch()`, not a native form POST**:
  - On submit, prevent the default action and `fetch('/login', { method: 'POST', body: new FormData(form) })`.
  - Parse the JSON response.
  - **On success** (`data.success` truthy): navigate via `window.location.href = data.redirect` (i.e. `/welcome`).
  - **On failure**: render `data.error` into the inline error area — light red background, red border, dark red text — **without a page reload** and without a browser `alert()` (spec §3.2, §6.2, TC-06).
- **Input styling**: `#f8f9ff` background, `1.5px solid #c5cae9` border; on focus the border becomes `#3949ab` with the focus-glow shadow `0 0 0 3px rgba(57,73,171,0.12)`.

### `signup.html`

- **Layout**: structurally identical to `login.html` — same split, same gradient, same decorative circles, same input/button styling.
- **Form**: a standard HTML form with `action="/signup"` and `method="POST"` — a **native browser submission**, deliberately *not* `fetch()` (spec §13 rule 4).
- **Fields**: `username`, `email`, `password`, `confirm_password`.
- **Client-side validation**: JS compares `password` against `confirm_password` **before** allowing submission. On mismatch, block the submit and show an inline red error span beneath the confirm field — no page reload, no request sent (spec §3.1, TC-04).

### `dashboard.html`

- **Body background**: `#eef1f8`.
- **Hero banner** beneath the shared header: gradient `#1a237e → #3949ab`.
  - Left: the title "Security Vulnerability Lab" plus a subtitle.
  - Right: "Logged in as `{{username}}`" plus a semi-transparent white logout button linking to `/logout`.
- **`{{username}}` is the substitution token** that Phase 5's `/welcome` handler replaces at request time. It must appear **literally** in this file — do not pre-render it, and do not switch to a Jinja2 expression (there is no template engine in this project).
- **Content area**: max-width 1100px, centered.
  - **Mission card**: white, with a section title and descriptive body text.
  - **"Vulnerabilities to Discover"**: an uppercase, small, bold section header above a **two-column grid of 8 vulnerability cards**. Each card is white, rounded, lightly bordered, lifts with the card-hover shadow (`0 4px 16px rgba(26,35,126,0.10)`), and carries a colored pill tag plus a description. Tag colors: **SQLi = yellow, XSS = red, Session = purple, Brute = orange, Crypto = green, Exposed = blue, CSRF = pink**.
  - **Three process step cards** — "Find", "Exploit", "Mitigate" — each with `#1a237e` background, a circular numbered badge, and white text.

---

## Phase 8: Styling

### File: `frontend/static/css/styles.css`

A single stylesheet implementing the complete design system from spec §5. No CSS framework, no preprocessor, no build step.

**Typography**: family `Segoe UI, system-ui, -apple-system, sans-serif`. Scale — main titles 2rem/800, section titles 1.4rem/700, form titles 1.7rem/700, card titles 0.95rem/700, body 0.9rem/400, labels 0.82rem/600, buttons 1rem/600.

**Colors** — primary: `#1a237e`, `#3949ab`, `#283593`, `#0f172a`, `#eef1f8`, `#ffffff`. Text: `#1e293b` (primary), `#475569` (secondary), `#64748b` (muted), `#c5cae9` (on dark), `#1a237e` (headings).

**Border radius**: inputs 8px, buttons 8px, cards 10–12px, status tags 6px.

**Shadows**: header `0 2px 10px rgba(26,35,126,0.08)`; card hover `0 4px 16px rgba(26,35,126,0.10)`; focus glow `0 0 0 3px rgba(57,73,171,0.12)`.

**Layout mechanics**: CSS Grid for the auth split-screen and the dashboard's 8-card grid; Flexbox for the header, hero banner, and process-step row.

**Responsive behavior** (spec §5.6): on narrow viewports the auth pages stack vertically instead of splitting side-by-side, the dashboard's vulnerability grid collapses to a single column, the process-step cards stack vertically, and the header logos shrink to fit.

---

## Phase 9: Project Instructions

### File: `CLAUDE.md` (project root)

A guidance document for anyone (human or AI) working in this repo. Sections:

1. **Project Context** — that this is an intentionally vulnerable educational app, that all 8 flaws are deliberate, and the explicit warning that they must not be "fixed" without an accompanying spec that says so.
2. **Development Commands** — install (`cd backend && uv sync`), run (`uv run backend/app/main.py` from the project root), and the access URL `http://localhost:3001`.
3. **Architecture Overview** — the three-layer split (Presentation → Application → Data) and an annotated file tree.
4. **Vulnerability Map** — the table from the top of this plan: each vulnerability, its file, and its mechanism.
5. **Frontend-Backend Integration** — login via `fetch()`/JSON, signup via native form POST, dashboard via `str.replace('{{username}}', ...)` with no template engine.
6. **Security Education Context** — the ethical-use boundary: localhost only, never production, never the public internet, never real data.
7. **Specification Hierarchy** — the document precedence order: `docs/PRD.md` → `docs/TDD.md` → `.claude/specs/app-foundation.md` → `.claude/specs/app-foundation-plan.md`, plus a pointer to `docs/prompts/` for the prompts that generated each artifact.

---

## Phase 10: Testing and Validation

Manual verification — no automated test suite ships in this baseline (`pytest` is declared as an optional dev dependency in Phase 1 for future use only).

### Startup

1. From the project root, run `uv run backend/app/main.py`.
2. Confirm the server binds to port 3001 and `vulnerable_app.db` appears at the project root on first launch.
3. Open `http://localhost:3001` — it must redirect to `/signup`.

### Functional flows

| Check | Steps | Expected | Spec ref |
|---|---|---|---|
| Pages load | Visit `/signup`, `/login` | Both render with header, logos, split-screen layout, and CSS applied | AC-01/02 |
| Signup succeeds | Submit valid, unique data | Row created; redirected to `/login` | SP-01, TC-01 |
| Duplicate username | Submit an existing username | "Username already exists"; no redirect | AP-01, TC-02 |
| Password mismatch | Enter differing password/confirm | Inline red message; **no request sent** | TC-04 |
| Login succeeds | Submit valid credentials | JSON success; JS redirects to `/welcome`; dashboard shows the username | SP-02, TC-05 |
| Login fails | Submit a wrong password | 401 JSON; error rendered inline; **no page reload**; no session | AP-02, TC-06 |
| Session protection | Request `/welcome` in a fresh browser | Redirected to `/login` | AP-03, TC-09 |
| Logout clears session | Log in → log out → request `/welcome` | Redirected to `/login` | SP-04, TC-10 |
| Search matches | `/search?q=<existing user>` | Matching rows rendered | AC-05, TC-11 |
| Template hot-edit | Edit a template, re-request without restarting | Change visible immediately | TC-14 |
| Restart persistence | Register → restart app → log in again | Login succeeds; data survived | AC-06, TC-15 |

### Vulnerability verification

These confirm the flaws are actually present. **A failure here means the implementation is wrong** — it means something got "fixed" that shouldn't have been.

| # | Check | Expected |
|---|---|---|
| 1 | Log in with username `admin' OR '1'='1' --` and any password | Authentication bypassed — session established without a valid password |
| 2 | Register username `<img src=x onerror=alert('XSS')>`, then log in | Alert fires on the dashboard |
| 3 | Visit `/search?q=<img src=x onerror=alert(1)>` | Alert fires immediately |
| 4 | Read `main.py` | `SECRET_KEY` is the literal `"super-secret-key-12345"`; copying a session cookie into another browser grants access |
| 5 | Download the DB and inspect the `password` column | Values are 32-char unsalted MD5 hex digests, reversible via rainbow tables |
| 6 | Visit `/download/db` while logged out | The SQLite file downloads with no auth challenge |
| 7 | Script rapid repeated `POST /login` attempts | No throttling, no 429, no lockout — all attempts processed |
| 8 | Host an external HTML form targeting `/signup`, submit it | Request succeeds; no CSRF token demanded |

### Final completeness check

- All 11 backend files exist, with the 5 `__init__.py` files empty.
- All 3 templates and `styles.css` exist; the 3 logo images are unmodified.
- Every SQL statement in `auth_service.py` and `auth.py` is built by **string concatenation** — grep for `?` placeholders and `execute(` with a parameter tuple; there should be **none**.
- `CLAUDE.md` exists at the project root.
- All 8 rows of the Vulnerability Map are accounted for, including the two omission-based ones (#7, #8).

---

## Out of Scope for This Plan

Deferred to later specs, per `docs/PRD.md` §1.3 and §7:

- Remediation of any of the 8 vulnerabilities (each fix is its own later spec + plan + tag).
- Dark mode, password strength meter, profile page, OAuth, email verification, MFA, or any other feature enhancement.
- Docker packaging, CI/CD, cloud deployment.
- An automated test suite (`pytest` is declared but unused).
- Any additional vulnerability beyond the 8 specified (no command injection, XXE, SSRF, IDOR, or file-upload flaws).
