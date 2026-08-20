# Software Specification Document (Remediation Addendum)

## Vulnerable Web Application — Stored XSS Remediation

**Version:** 1.0.0
**Companion Documents:** `docs/PRD.md`, `docs/TDD.md`, `.claude/specs/app-foundation.md`, `.claude/specs/bcrypt-password-hashing.md`, `.claude/specs/sql-injection-fix.md`, `.claude/specs/session-hijacking-fix.md`

---

## 1. Overview / Purpose

This document specifies the remediation of **VULN-2 (Stored XSS)** in `backend/app/api/routes/auth.py`'s `welcome_page()`. The route substitutes `request.session["username"]` directly into the dashboard template's `{{username}}` placeholder via unescaped `str.replace()`. Because a username is attacker-controlled at signup time (nothing in the foundation validates or sanitizes it) and is persisted verbatim, a username registered as a payload such as `<script>alert(1)</script>` is stored once and then executes in the browser of anyone whose session renders that dashboard — including the attacker's own subsequent logins, and, more seriously, any other session context in which that stored value is later rendered.

This addendum closes the flaw by HTML-escaping the session's `username` value — using Python's standard-library `html.escape()` — immediately before it is substituted into the `{{username}}` placeholder, so the byte sequence reaching the browser can never be interpreted as executable markup. The template mechanism itself (per-request disk read of `dashboard.html`, plain `str.replace()` substitution, no templating engine) is unchanged; only the value being substituted is transformed first.

---

## 2. Scope & Non-Goals

### In Scope
- **VULN-2 — Stored XSS**: HTML-escape `request.session["username"]` in `welcome_page()` (`backend/app/api/routes/auth.py`) before it is substituted into `dashboard.html`'s `{{username}}` placeholder.

### Non-Goals (remain intentionally unfixed)
This spec closes **vulnerability #2 only**. The following vulnerabilities are explicitly **out of scope** and must not be altered by this change:

| # | Vulnerability | Status |
|---|---|---|
| 3 | Reflected XSS (and its bundled SQL Injection) in `/search` (`backend/app/api/routes/auth.py`) | Untouched. Do not escape the `q` reflection, the result rows, or the exception text, and do not parameterize the query. |
| 6 | Exposed Database (`GET /download/db`) | Untouched. No authentication is added. |
| 7 | No Rate Limiting | Untouched. No throttling middleware is added. |
| 8 | CSRF | Untouched. No CSRF token or validation is added to any form or route. |

**Vulnerabilities #1, #4, and #5, plus the dark mode toggle, are already fixed/implemented** (parameterized queries per `.claude/specs/sql-injection-fix.md`, hardened session config per `.claude/specs/session-hijacking-fix.md`, bcrypt hashing per `.claude/specs/bcrypt-password-hashing.md`, and the presentational theme switch per `.claude/specs/dark-mode-toggle.md`) and are explicitly **outside the scope of this task**. Do not modify `backend/app/services/auth_service.py`, `backend/app/core/security.py`, or `backend/app/main.py`, and do not touch any dark-mode-related frontend files.

This fix must not introduce a template engine, must not change how `dashboard.html` is loaded (still read fresh from disk per request, no caching), and must not change the `{{username}}` placeholder token or its location in `dashboard.html` itself.

---

## 3. Affected Files

**To be modified:**
- `backend/app/api/routes/auth.py` — in `welcome_page()`, escape `request.session["username"]` with `html.escape()` before substituting it into the `{{username}}` placeholder.

**Inspected but must NOT be modified:**
- `frontend/templates/dashboard.html` — the `{{username}}` placeholder and surrounding markup are unchanged; the fix only changes the value substituted into it, not the template.
- `backend/app/services/auth_service.py` — signup/login logic and parameterized queries (VULN-1, already fixed); untouched by this task.
- `backend/app/core/security.py` — bcrypt hashing (VULN-5, already fixed); untouched by this task.
- `backend/app/main.py` — session middleware configuration (VULN-4, already fixed); untouched by this task.
- `backend/app/api/routes/auth.py`'s `/search` route (VULN-3) and `/download/db` route (VULN-6) — must remain exactly as-is.
- `backend/pyproject.toml`, `pyproject.toml` (root) — no new dependency is required; `html.escape()` is part of the Python standard library (`html` module).

---

## 4. Functional Requirements

### FR-01: Escape Username Before Substitution
`welcome_page()` must pass `request.session["username"]` through `html.escape()` and substitute the **escaped** result into `dashboard.html`'s `{{username}}` placeholder, replacing the current unescaped substitution.

### FR-02: Escaping Applied Only at the Point of Substitution
The escaping transformation must be applied only to the value used for the `{{username}}` substitution in `welcome_page()`. The raw, unescaped username as stored in the database and as stored in `request.session["username"]` is not otherwise altered, re-encoded, or re-written by this fix — signup, login, and session population are unchanged.

### FR-03: Template Mechanism Unchanged
`dashboard.html` must continue to be read fresh from disk on every request (no caching) and the substitution must continue to use plain `str.replace("{{username}}", ...)`. No templating engine (e.g., Jinja2) may be introduced.

### FR-04: No Unrelated Vulnerability Fixes
This change must not escape or otherwise alter the `/search` route's reflected `q` parameter, result rows, or exception text (VULN-3), must not add authentication to `/download/db` (VULN-6), and must not add rate-limiting or CSRF middleware (VULN-7/VULN-8).

---

## 5. Non-Functional Requirements

### NFR-01: Standard Library Only
The fix must use Python's standard-library `html.escape()` (from the `html` module). No new package may be added to `backend/pyproject.toml` or the root `pyproject.toml`.

### NFR-02: Response Behavior Preserved for Non-Attack Input
For a normal alphanumeric username, the returned dashboard HTML must be byte-for-byte identical to its pre-fix output — `html.escape()` on input containing no `&`, `<`, `>`, `"`, or `'` characters is a no-op.

### NFR-03: Route Contract Unchanged
`welcome_page()`'s authentication check (redirect to `/login` when `user_id` is absent from the session), status codes, and response type (`HTMLResponse`) are unchanged. Only the value substituted for `{{username}}` changes.

### NFR-04: Consistent with Existing Code Style
The fix must be a small, local change inside `welcome_page()` (an `html.escape()` call plus an updated import), consistent with the file's existing minimal, dependency-light style — not a broader refactor of the route or the template-loading helper.

---

## 6. Success Paths

**SP-01 — Normal username renders unchanged**: an authenticated user with an ordinary alphanumeric username (e.g. `alice123`) requests `/welcome` → `html.escape()` is a no-op on this input → the dashboard HTML is visually and byte-for-byte identical to pre-fix behavior.

**SP-02 — Script-payload username renders as inert text**: a user previously registered with `username = "<script>alert(1)</script>"` (permitted because signup performs no username sanitization) logs in and requests `/welcome` → the substituted value is `&lt;script&gt;alert(1)&lt;/script&gt;` → the browser renders this as literal visible text inside the `user-badge` span (e.g. "Logged in as &lt;script&gt;alert(1)&lt;/script&gt;") and does **not** execute any script.

**SP-03 — Username containing HTML-significant characters renders correctly escaped**: a username containing any of `&`, `<`, `>`, `"`, `'` (e.g. `O'Brien & <Co>`) is stored at signup and later substituted into the dashboard → each such character is rendered as its corresponding HTML entity (`&amp;`, `&lt;`, `&gt;`, `&quot;`/`&#x27;` per `html.escape()`'s defaults) and displays as the correct literal character to the user, with no markup interpretation.

---

## 7. Edge Cases

**EC-01 — `<script>` tag payload**: `username = "<script>alert(1)</script>"` → rendered dashboard HTML contains `&lt;script&gt;alert(1)&lt;/script&gt;` inside the `user-badge` span; no `<script>` element is parsed or executed by the browser.

**EC-02 — `<img onerror=...>` payload**: `username = "<img src=x onerror=alert(1)>"` → rendered as `&lt;img src=x onerror=alert(1)&gt;`; no `<img>` element is created and no event handler fires.

**EC-03 — Ampersand in username**: `username = "Smith & Sons"` → rendered as `Smith &amp; Sons`, displaying as `Smith & Sons` in the browser, not double-escaped or truncated.

**EC-04 — Angle brackets without a full tag**: `username = "5 < 10 > 3"` → rendered as `5 &lt; 10 &gt; 3`, displaying correctly with no broken markup.

**EC-05 — Double quote in username**: `username = "the \"boss\""` → the `"` characters are escaped (`&quot;` under `html.escape()`'s default `quote=True` behavior) so the value cannot break out of any surrounding double-quoted HTML attribute.

**EC-06 — Single quote / apostrophe in username**: `username = "O'Brien"` → the `'` character is escaped (`&#x27;` under `html.escape()`'s default `quote=True` behavior) so the value cannot break out of any surrounding single-quoted HTML attribute.

**EC-07 — Attribute-breakout attempt**: `username = "x\" onmouseover=\"alert(1)"` → the `"` characters are escaped, so the payload cannot terminate an existing HTML attribute or inject a new one; it renders as inert literal text.

**EC-08 — Empty or purely whitespace username**: not newly introduced by this fix (username is required non-empty at signup per `app-foundation.md` §7); `html.escape()` on any such value is still safe and produces no error.

**EC-09 — Non-Latin / Unicode username**: `username = "日本語ユーザー"` → contains no HTML-significant characters, so `html.escape()` is a no-op and the username displays unchanged.

---

## 8. Acceptance Criteria

**AC-01**: Given the source of `welcome_page()`, when reviewed, then `request.session["username"]` is passed through `html.escape()` (from the standard-library `html` module) before being substituted into the `{{username}}` placeholder.

**AC-02**: Given a session with `username = "<script>alert(1)</script>"`, when `GET /welcome` is requested, then the response body contains the literal escaped sequence `&lt;script&gt;alert(1)&lt;/script&gt;` and does **not** contain an unescaped `<script>` tag.

**AC-03**: Given a session with a username containing `&`, `<`, `>`, `"`, or `'`, when `GET /welcome` is requested, then each such character appears in the response body as its corresponding HTML entity, not as the raw character.

**AC-04**: Given a session with a normal alphanumeric username, when `GET /welcome` is requested, then the response body is unchanged from pre-fix behavior (escaping is a no-op).

**AC-05**: Given `dashboard.html`, when compared to its pre-fix state, then it is byte-for-byte unchanged — the fix is contained entirely within `welcome_page()` in `auth.py`.

**AC-06**: Vulnerability #2 (Stored XSS via `/welcome`'s `{{username}}` substitution) is considered fixed.

**AC-07**: Vulnerabilities #3, #6, #7, #8 remain intentionally unchanged, including the reflected XSS and SQL injection in `/search`.

---

## 9. Test Cases

| ID | Scenario | Precondition | Expected Result |
|---|---|---|---|
| TC-01 | Normal username renders unchanged | User registered with `username = "alice123"`, logged in | `GET /welcome` returns HTML with `Logged in as alice123`; output byte-identical to pre-fix behavior |
| TC-02 | `<script>` payload does not execute | User registered with `username = "<script>alert(1)</script>"`, logged in | `GET /welcome` response body contains `&lt;script&gt;alert(1)&lt;/script&gt;`; no raw `<script>` tag present; loading the page in a browser shows no alert |
| TC-03 | `<img onerror>` payload does not execute | User registered with `username = "<img src=x onerror=alert(1)>"`, logged in | Response body contains the fully escaped entity sequence; no `<img>` tag is parsed; no alert fires |
| TC-04 | Ampersand escapes correctly | User registered with `username = "Smith & Sons"`, logged in | Response body contains `Smith &amp; Sons` |
| TC-05 | Less-than / greater-than escape correctly | User registered with `username = "5 < 10 > 3"`, logged in | Response body contains `5 &lt; 10 &gt; 3` |
| TC-06 | Double quote escapes correctly | User registered with `username = "the \"boss\""`, logged in | Response body contains `&quot;` in place of each `"` |
| TC-07 | Single quote escapes correctly | User registered with `username = "O'Brien"`, logged in | Response body contains `&#x27;` in place of `'` |
| TC-08 | Attribute-breakout payload is inert | User registered with `username = "x\" onmouseover=\"alert(1)"`, logged in | Response body contains the value with `"` escaped to `&quot;`; no new HTML attribute is created |
| TC-09 | Unauthenticated dashboard access unaffected | No prior login | `GET /welcome` redirects to `/login`, exactly as pre-fix |
| TC-10 | `/search` reflected XSS remains unfixed | None | `GET /search?q=<script>alert(1)</script>` still reflects the payload unescaped in the response body |
| TC-11 | `/download/db` remains unauthenticated | None | `GET /download/db` still returns the SQLite file with no auth check |

---

## 10. Verification Steps

1. Install dependencies (no new dependency is added, but confirm the environment is current):
   ```
   cd backend && uv sync
   ```
2. Start the application from the project root:
   ```
   uv run backend/app/main.py
   ```
3. The application is served at `http://localhost:3001`.
4. Register a test account with a script-payload username (TC-02):
   ```
   curl -i -X POST http://localhost:3001/signup \
     --data-urlencode "username=<script>alert(1)</script>" \
     -d "email=xsstest@example.com" \
     -d "password=SomePassword123"
   ```
   Confirm signup succeeds (`302` to `/login`).
5. Log in as that user and capture the session cookie:
   ```
   curl -i -c cookies.txt -X POST http://localhost:3001/login \
     --data-urlencode "username=<script>alert(1)</script>" \
     -d "password=SomePassword123"
   ```
   Confirm `200` and JSON `{"success": true, "redirect": "/welcome"}`.
6. Request the dashboard using the saved session and inspect the raw response body (AC-02):
   ```
   curl -s -b cookies.txt http://localhost:3001/welcome
   ```
   Confirm the body contains the literal text `&lt;script&gt;alert(1)&lt;/script&gt;` and does **not** contain an unescaped `<script>alert(1)</script>` tag.
7. Open `http://localhost:3001/welcome` in a browser with the same session cookie (or log in via the UI with this username) and confirm no JavaScript `alert()` dialog appears, and that the visible "Logged in as" text shows the payload as literal text.
8. Repeat steps 4–6 for a username containing `&`, `<`, `>`, `"`, `'` individually (EC-03 through EC-07) and confirm each character appears HTML-entity-encoded in the response body.
9. Confirm a normal alphanumeric username is unaffected (TC-01):
   ```
   curl -i -X POST http://localhost:3001/signup \
     -d "username=alice123" -d "email=alice@example.com" -d "password=SomePassword123"
   curl -i -c cookies2.txt -X POST http://localhost:3001/login \
     -d "username=alice123" -d "password=SomePassword123"
   curl -s -b cookies2.txt http://localhost:3001/welcome
   ```
   Confirm the response contains `Logged in as alice123` with no entity-encoding artifacts.
10. Confirm `/search` (VULN-3) remains unescaped (TC-10):
    ```
    curl -s "http://localhost:3001/search?q=<script>alert(1)</script>"
    ```
    Confirm the payload is reflected unescaped in the response body.
11. Confirm `/download/db` (VULN-6) remains unauthenticated (TC-11):
    ```
    curl -i http://localhost:3001/download/db
    ```
    Confirm `200` and a binary SQLite file is returned with no auth check.
12. Confirm the fix is source-level and localized (AC-01, AC-05) by inspecting `backend/app/api/routes/auth.py`'s `welcome_page()` for an `html.escape()` call on `request.session["username"]`, and by diffing `frontend/templates/dashboard.html` against its pre-fix state:
    ```
    git diff HEAD -- frontend/templates/dashboard.html
    ```
    Expect no output (no changes).
13. If the repository's `dev` extra test suite is used, run it from `backend/`:
    ```
    cd backend && uv run --extra dev pytest
    ```
