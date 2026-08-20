# Software Specification Document (Remediation Addendum)

## Vulnerable Web Application — SQL Injection Remediation

**Version:** 1.0.0
**Companion Documents:** `docs/PRD.md`, `docs/TDD.md`, `.claude/specs/app-foundation.md`, `.claude/specs/bcrypt-password-hashing.md`

---

## 1. Overview / Purpose

This document specifies the remediation of **VULN-1 (SQL Injection)** in `backend/app/services/auth_service.py`. Both `signup()`'s `INSERT` and `login()`'s username-lookup `SELECT` build their SQL statements by concatenating raw, user-controlled strings (`username`, `email`, `password` hash) directly into the query text. An attacker who controls the `username` or `email` field can inject arbitrary SQL — most notably, a crafted `username` in `login()` (e.g. `' OR '1'='1' --`) can alter the `WHERE` clause and return a row without knowing any valid credentials, bypassing authentication entirely.

This addendum replaces string concatenation in both queries with **parameterized queries** (`sqlite3`'s `?` placeholder binding), so user input is always passed as data and can never change the structure of the SQL statement. Password verification already happens in Python via `verify_password()` since the `v0.1.1` bcrypt remediation (`.claude/specs/bcrypt-password-hashing.md`); this fix does not touch that flow — it only changes how the user row is fetched and how the new row is inserted.

---

## 2. Scope & Non-Goals

### In Scope
- **VULN-1 — SQL Injection**: replace string-concatenated SQL in `auth_service.signup()` (`INSERT`) and `auth_service.login()` (`SELECT`) with parameterized queries using `sqlite3`'s `?` placeholder style.
- Preserving all existing authentication behavior, response shapes, and the bcrypt-based password verification flow introduced in `v0.1.1`.

### Non-Goals (remain intentionally unfixed)
The following 6 vulnerabilities are explicitly **out of scope** and must not be altered by this change:

| # | Vulnerability | Status |
|---|---|---|
| 2 | Stored XSS (`/welcome` `{{username}}` substitution) | Untouched. |
| 3 | Reflected XSS **and** its accompanying SQL Injection in `/search` (`backend/app/api/routes/auth.py`) | Untouched. The `/search` query is also built via string concatenation, but it is bundled under VULN-3 (Reflected XSS) in the project's vulnerability map, not VULN-1 — it is explicitly **not** part of this task. Do not parameterize it and do not escape its output. |
| 4 | Session Hijacking (hardcoded `SECRET_KEY`) | Untouched. |
| 6 | Exposed Database (`GET /download/db`) | Untouched. |
| 7 | No Rate Limiting | Untouched. |
| 8 | CSRF | Untouched. |

**Vulnerability #5 (weak password storage) and the dark mode toggle are already fixed/implemented in `v0.1.1`** (bcrypt hashing per `.claude/specs/bcrypt-password-hashing.md`, and the presentational theme switch per `.claude/specs/dark-mode-toggle.md`) and are explicitly **outside the scope of this task**. Do not modify `backend/app/core/security.py`, do not revert or weaken bcrypt hashing/verification, and do not touch any dark-mode-related frontend files.

This spec closes **vulnerability #1 only**, and only within `auth_service.py`'s `signup()` and `login()` queries.

---

## 3. Affected Files

**To be modified:**
- `backend/app/services/auth_service.py` — replace the concatenated `INSERT` in `signup()` and the concatenated `SELECT` in `login()` with parameterized (`?`-placeholder) queries.

**Inspected but must NOT be modified:**
- `backend/app/core/security.py` — bcrypt `hash_password()`/`verify_password()` implementation; already fixed in `v0.1.1`, untouched by this task.
- `backend/app/api/routes/auth.py` — the `/search` route's SQL injection and reflected XSS (VULN-3) and the `/download/db` route (VULN-6) must remain exactly as-is.
- `backend/app/db/session.py` — `get_db()`/`init_db()` connection and schema setup; no schema change is required or permitted.
- `backend/pyproject.toml`, `pyproject.toml` (root) — no new dependency is required; `sqlite3`'s parameter-binding support is part of the Python standard library already in use.

---

## 4. Functional Requirements

### FR-01: Parameterized Login Query
`auth_service.login()` must replace the string-concatenated `SELECT * FROM users WHERE username = '" + username + "'"` with a parameterized query using `?` placeholders and a bound parameter tuple, e.g. `conn.execute("SELECT * FROM users WHERE username = ?", (username,))`.

### FR-02: Parameterized Signup Query
`auth_service.signup()` must replace the string-concatenated `INSERT INTO users (...) VALUES ('...')` with a parameterized query using `?` placeholders and a bound parameter tuple for `username`, `email`, and the bcrypt `hashed` value, e.g. `conn.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)", (username, email, hashed))`.

### FR-03: Username Cannot Alter Query Structure
After the fix, no value supplied in the `username` field (at signup or login) may change the number of clauses, tables, or columns referenced by the executed SQL — the query text itself must be a fixed string, with only the bound parameter values varying per request.

### FR-04: Existing Bcrypt Verification Flow Preserved
`login()` must continue to: (1) fetch the user row by `username` only, (2) if a row is found, call the existing `verify_password(password, row["password"])` from `backend/app/core/security.py`, and (3) treat "no row found" and "row found but `verify_password()` returns `False`" identically — `401` with the existing `{"success": False, "error": "Invalid username or password."}` payload. None of this control flow changes; only how the row is fetched changes.

### FR-05: Bcrypt Implementation Untouched
`backend/app/core/security.py` must not be modified. `hash_password()` and `verify_password()` keep their exact `v0.1.1` implementation and behavior.

### FR-06: No Unrelated Vulnerability Fixes
This change must not parameterize, escape, or otherwise alter the `/search` route's query or output (VULN-3), add authentication to `/download/db` (VULN-6), change `SECRET_KEY` sourcing (VULN-4), escape the `/welcome` `{{username}}` substitution (VULN-2), or add rate-limiting/CSRF middleware (VULN-7/VULN-8).

---

## 5. Non-Functional Requirements

### NFR-01: No String-Built SQL for User Input
No raw user-controlled value (`username`, `email`, or the bcrypt `hashed` password string) may be interpolated, formatted, or concatenated into SQL statement text in `signup()` or `login()`. All such values must be passed exclusively via the parameter-binding tuple argument to `conn.execute()`.

### NFR-02: API Behavior Preserved
Response payloads, status codes, and redirect targets for `signup()` and `login()` must remain byte-for-byte identical in structure and content to their `v0.1.1` behavior for all non-attack inputs (success, duplicate username, missing fields, wrong password, nonexistent username). No change to response format is required or permitted by this fix.

### NFR-03: Consistent with Existing Database-Access Style
The parameterized queries must use the same `sqlite3` connection pattern already in place (`get_db()`, `conn.execute(...)`, `conn.commit()`/`conn.close()` in `finally`/inline as currently structured) — i.e., use `sqlite3`'s native `?` placeholder + tuple binding, not a new query-building abstraction, ORM, or query builder.

### NFR-04: No New Dependencies
`sqlite3` (Python standard library) already supports parameterized queries natively via `conn.execute(query, params)`. No new package must be added to `backend/pyproject.toml` or the root `pyproject.toml` for this fix.

---

## 6. Success Paths

**SP-01 — Successful login with correct username/password**: an existing user submits their correct `username` and `password` → `login()` fetches the row via a parameterized `SELECT ... WHERE username = ?` → `verify_password()` returns `True` → session established, `200`/JSON `{"success": true, "redirect": "/welcome"}` as before.

**SP-02 — Failed login with an incorrect password**: an existing user submits their correct `username` but a wrong `password` → the parameterized `SELECT` returns the row → `verify_password()` returns `False` → `401` with the generic invalid-credentials error, exactly as in `v0.1.1`.

**SP-03 — Failed login with a nonexistent username**: a `username` with no matching row is submitted → the parameterized `SELECT` returns no row → `401` with the same generic invalid-credentials error (indistinguishable from SP-02).

**SP-04 — Usernames with characters that previously required escaping**: a `username` or `email` containing characters such as `'`, `"`, or `-` (e.g. `O'Brien`, `d'angelo@example.com`) is submitted at signup and later used to log in. Because the value is bound as a parameter rather than concatenated into SQL text, no manual escaping is needed; the value is stored and matched exactly as entered, and signup/login both succeed normally.

---

## 7. Edge Cases

**EC-01 — SQL injection payload in the username field**: a `login()` or `signup()` request submits a `username` such as `' OR '1'='1' --` or `' OR '1'='1`. Because the value is bound as a parameter, it is treated as a literal string to match/insert, not as SQL syntax — no row matches (login) or a literal odd-looking username is stored (signup); no query-structure change occurs.

**EC-02 — SQL injection payload in the password field**: a `login()` request submits a `password` such as `' OR '1'='1' --`. The password value is never part of the SQL query (it is only used by `verify_password()` in Python after the row is fetched by username), so this payload has no effect on the SQL query in either the pre-fix or post-fix code; it is simply compared as a plain string against the stored bcrypt hash and fails verification normally.

**EC-03 — Quotes, comments, and operators in input**: inputs containing single quotes (`'`), SQL comment sequences (`--`, `/* */`), boolean operators (`OR`, `AND`), or `UNION SELECT` fragments, submitted in `username` or `email`, must not alter query semantics, return unexpected rows, or change the number of columns/tables referenced — the query text is fixed regardless of parameter content.

**EC-04 — Injection attempt results in normal auth failure, not bypass/error/crash**: a classic authentication-bypass payload (e.g. `username = "' OR '1'='1' --"`, any `password`) submitted to `/login` must result in a normal `401 Unauthorized` JSON response (`{"success": false, "error": "Invalid username or password."}`), never a successful login, a SQL error, an exposed stack trace, or a `500`.

**EC-05 — Bcrypt password verification remains intact**: after the fix, a legitimately registered user's login must still route through `verify_password()` exactly as in `v0.1.1` — fetch row by username (now parameterized), then verify the bcrypt hash in Python. This flow must not be bypassed, reordered, or short-circuited by the SQL fix.

**EC-06 — No reintroduction of plaintext/MD5 comparison**: the fix must not move password comparison back into the SQL `WHERE` clause, must not compare `password` as plaintext, and must not reintroduce MD5 or any hashing scheme other than the existing bcrypt implementation in `security.py`.

---

## 8. Acceptance Criteria

**AC-01**: Given the source of `login()`, when reviewed, then the `SELECT` query uses a `?` placeholder for `username` with the value passed via a bound parameter tuple to `conn.execute()`, not string concatenation or f-string/`.format()` interpolation.

**AC-02**: Given the source of `signup()`, when reviewed, then the `INSERT` query uses `?` placeholders for `username`, `email`, and the hashed password, with values passed via a bound parameter tuple to `conn.execute()`, not string concatenation.

**AC-03**: Given a known SQL injection authentication-bypass payload (e.g. `username = "' OR '1'='1' --"`) submitted to `POST /login`, when processed, then authentication is **not** bypassed — the response is `401` with the standard invalid-credentials error.

**AC-04**: Given a legitimately registered user, when they submit correct credentials to `POST /login`, then login still succeeds (`200`/JSON `{"success": true, "redirect": "/welcome"}`) and the session is populated exactly as in `v0.1.1`.

**AC-05**: Given a legitimately registered user, when they submit an incorrect password or a nonexistent username to `POST /login`, then the response is still `401` with the standard invalid-credentials error, byte-for-byte identical to `v0.1.1` behavior.

**AC-06**: Given any injection payload submitted via `username`, `email`, or `password` to `/login` or `/signup`, when processed, then no SQL exception, stack trace, or `500` response is ever exposed to the client as a result of that input.

**AC-07**: Vulnerability #1 (SQL Injection in `auth_service.py`) is considered fixed.

**AC-08**: Vulnerabilities #2, #3, #4, #6, #7, #8 remain intentionally unchanged, including the SQL injection bundled with VULN-3 in `/search`.

**AC-09**: Given `backend/app/core/security.py`, when compared to its `v0.1.1` state, then it is byte-for-byte unchanged — the bcrypt fix from `v0.1.1` remains fully intact.

---

## 9. Test Cases

| ID | Scenario | Precondition | Expected Result |
|---|---|---|---|
| TC-01 | Normal successful login | User registered with known username/password under `v0.1.1` bcrypt scheme | `200`/JSON `{"success": true, "redirect": "/welcome"}`; session populated with `user_id`, `username`, `email` |
| TC-02 | Wrong password | User exists; correct username, incorrect password submitted | `401` JSON `{"success": false, "error": "Invalid username or password."}`; no session established |
| TC-03 | Nonexistent username | No user exists with the submitted username | `401` JSON `{"success": false, "error": "Invalid username or password."}`; no session established |
| TC-04 | SQL injection via username at login | None | `username = "' OR '1'='1' --"`, any `password` → `401` JSON error, no session, no `500` |
| TC-05 | SQL injection via password at login | An existing user account exists | Correct `username`, `password = "' OR '1'='1' --"` → `401` JSON error (payload never reaches SQL; fails bcrypt verification as a literal string) |
| TC-06 | Username containing a single quote | None | Signup with `username = "O'Brien"` succeeds; subsequent login with that exact username and its correct password succeeds (`200`) |
| TC-07 | SQL comment/operator-based injection attempt | None | `username = "admin'--"` or `username = "' UNION SELECT 1,2,3,4 --"` submitted to `/login` → `401` JSON error, no rows improperly returned, no `500` |
| TC-08 | Authentication-bypass payload returns 401, not a crash | None | `username = "' OR '1'='1"`, `password = "anything"` submitted to `POST /login` → response is `401`, response body is valid JSON with the standard error message, server logs show no unhandled exception/traceback |
| TC-09 | Bcrypt verification still works after the SQLi fix | User registered under the bcrypt scheme (post-`v0.1.1`) | Correct login succeeds (`200`); `security.py` remains unmodified; `verify_password()` is still invoked in Python after the parameterized `SELECT` |

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
3. The application is served at `http://localhost:3001`. The login endpoint is:
   ```
   POST http://localhost:3001/login
   Content-Type: application/x-www-form-urlencoded (fields: username, password)
   ```
4. Register a normal test account first via the signup form at `http://localhost:3001/signup` (or `POST http://localhost:3001/signup` with `username`, `email`, `password` form fields), then verify a normal valid login (TC-01):
   ```
   curl -i -c cookies.txt -X POST http://localhost:3001/login \
     -d "username=<the-username-just-registered>" \
     -d "password=<the-correct-password>"
   ```
   Confirm `200` and JSON body `{"success": true, "redirect": "/welcome"}`.
5. Verify a normal invalid login (TC-02):
   ```
   curl -i -X POST http://localhost:3001/login \
     -d "username=<the-username-just-registered>" \
     -d "password=wrong-password"
   ```
   Confirm `401` and the standard invalid-credentials JSON error.
6. Verify the SQL injection authentication-bypass attempt no longer succeeds (TC-04 / TC-08 / AC-03):
   ```
   curl -i -X POST http://localhost:3001/login \
     --data-urlencode "username=' OR '1'='1' --" \
     --data-urlencode "password=anything"
   ```
   Confirm `401` and the standard invalid-credentials JSON error — not a `200`, not a `500`, and no stack trace in the response body or server console.
7. Verify a SQL comment/operator-based variant (TC-07):
   ```
   curl -i -X POST http://localhost:3001/login \
     --data-urlencode "username=admin'--" \
     --data-urlencode "password=anything"
   ```
   Confirm `401`, no `500`.
8. Verify SQL injection via the password field has no effect (TC-05):
   ```
   curl -i -X POST http://localhost:3001/login \
     -d "username=<the-username-just-registered>" \
     --data-urlencode "password=' OR '1'='1' --"
   ```
   Confirm `401` (the payload is compared as a literal string against the bcrypt hash and fails).
9. Verify a username containing a single quote can be registered and logged into (TC-06):
   ```
   curl -i -X POST http://localhost:3001/signup \
     --data-urlencode "username=O'Brien" \
     -d "email=obrien@example.com" \
     -d "password=SomePassword123"
   curl -i -c cookies2.txt -X POST http://localhost:3001/login \
     --data-urlencode "username=O'Brien" \
     -d "password=SomePassword123"
   ```
   Confirm signup succeeds (`302` to `/login`) and the subsequent login returns `200` with `{"success": true, "redirect": "/welcome"}`.
10. Confirm the fix is source-level parameterized (AC-01/AC-02) by inspecting `backend/app/services/auth_service.py` — both the `INSERT` in `signup()` and the `SELECT` in `login()` must use `?` placeholders with bound parameter tuples, not string concatenation.
11. Confirm `backend/app/core/security.py` is unmodified from its `v0.1.1` state (AC-09):
    ```
    git diff v0.1.1 -- backend/app/core/security.py
    ```
    Expect no output (no changes).
12. If the repository's `dev` extra test suite is used, run it from `backend/`:
    ```
    cd backend && uv run --extra dev pytest
    ```
