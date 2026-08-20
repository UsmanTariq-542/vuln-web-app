# Software Specification Document (Remediation Addendum)

## Vulnerable Web Application — Reflected XSS Fix (VULN-3)

**Version:** 1.0.0
**Companion Documents:** `docs/PRD.md`, `docs/TDD.md`, `.claude/specs/app-foundation.md`, `.claude/specs/sql-injection-fix.md`

---

## 1. Overview / Purpose

`GET /search` in `backend/app/api/routes/auth.py` currently builds its SQL query by concatenating the raw `q` query parameter directly into a `LIKE '%...%'` clause, embeds `q` and each matched row's `username`/`email` unescaped into the returned HTML, and — on any exception — returns the raw Python exception message in the response body. Per the route's own comment, these are three deliberately bundled issues filed together as **VULN-3 (Reflected XSS)** in this project's vulnerability map: reflected XSS via the unescaped `q` reflection and unescaped result rows, a SQL Injection via the same string-concatenated query, and information leakage via raw exception-message disclosure. This document specifies the remediation of all three, together, as a single fix to `search_user()`: parameterizing the SQL query with `?` placeholders (the same pattern already applied to `auth_service.py` for VULN-1), HTML-escaping every piece of user-influenced content before it is embedded in the response, and replacing the raw exception message with a generic, non-leaking error on failure — while preserving the route's existing shape (`GET /search?q=...` returning an HTML fragment).

---

## 2. Scope & Non-Goals

**In scope:** This document closes **VULN-3 only**, addressing all three issues bundled into the single `/search` route per the code's own comment (`backend/app/api/routes/auth.py`, `search_user()`):

1. The string-concatenated SQL query (`SELECT username, email FROM users WHERE username LIKE '%" + q + "%' OR email LIKE '%" + q + "%'"`) is replaced with a parameterized query using `?` placeholders and a bound parameter tuple.
2. `q` and each result row's `username`/`email` are HTML-escaped before being embedded into the returned HTML fragment.
3. The `except Exception as e:` handler's `HTMLResponse(f"<p>Search error: {e}</p>", status_code=500)` is replaced with a generic, non-leaking error message, still returned with a `500` status code, containing no exception text or stack detail.

**Out of scope / explicitly not touched:**

- **VULN-2** (Stored XSS in `/welcome`) — already remediated per `.claude/specs/stored-xss-fix.md`. Not touched by this document.
- **VULN-6** (Exposed Database) — already remediated per `.claude/specs/exposed-database-fix.md`. Not touched by this document.
- **VULN-7** (No Rate Limiting) — remains intentionally unfixed. Not touched by this document.
- **VULN-8** (CSRF) — remains intentionally unfixed. Not touched by this document.
- **VULN-1, VULN-4, VULN-5** — already remediated in prior work, unrelated to this route, and not touched by this document.

**Explicitly does NOT touch `auth_service.py` or the VULN-1 fix already applied there:** `backend/app/services/auth_service.py`'s `signup()`/`login()` queries were already parameterized under `.claude/specs/sql-injection-fix.md` as the VULN-1 remediation. That fix's own scope section explicitly excluded `/search`'s SQL injection, stating it is "bundled under VULN-3 (Reflected XSS) in the project's vulnerability map, not VULN-1" and is a separate task. This document is that separate task: it parameterizes a **different query, in a different file** (`search_user()`'s `SELECT` in `auth.py`, not `auth_service.py`'s `INSERT`/`SELECT`). No line of `auth_service.py` is read, referenced as a target, or modified by this fix — the two files' queries are independent and this fix touches only the one in `auth.py`.

**No new authorization or validation tier:** This fix does not add authentication to `/search`, does not add rate limiting to it, and does not add CSRF protection to it (those remain VULN-7/VULN-8, both out of scope). It also does not change the route's HTTP method, path, query-parameter name, or response content type — it remains an unauthenticated `GET /search?q=...` returning an `HTMLResponse` fragment.

---

## 3. Affected Files

| File | Change |
|---|---|
| `backend/app/api/routes/auth.py` | `search_user()`'s query is parameterized; `q` and result-row fields are HTML-escaped before embedding; the exception handler's response body is replaced with a generic message. |

**Inspected but must NOT be modified:**

- `backend/app/services/auth_service.py` — VULN-1's parameterized queries (`signup()`/`login()`); untouched, unrelated query in a different file.
- `backend/app/core/security.py` — bcrypt implementation; unrelated to this fix.
- `backend/app/db/session.py` — `get_db()`/`init_db()` connection and schema setup; no schema change is required or permitted.
- `backend/app/main.py` — session middleware/`SECRET_KEY` configuration; unrelated to this fix.
- No other route in `auth.py` (`index`, `signup_page`, `signup_post`, `login_page`, `login_post`, `download_db`, `welcome_page`, `logout`) is modified.

No new dependency is required; `sqlite3`'s parameter binding and Python's standard-library `html.escape()` (already imported in `auth.py` for the VULN-2 fix) are sufficient.

---

## 4. Functional Requirements

### FR-01: Parameterized Search Query
`search_user()` must replace the string-concatenated `SELECT username, email FROM users WHERE username LIKE '%" + q + "%' OR email LIKE '%" + q + "%'"` with a parameterized query using `?` placeholders and a bound parameter tuple, e.g. `conn.execute("SELECT username, email FROM users WHERE username LIKE ? OR email LIKE ?", (f"%{q}%", f"%{q}%"))`. The `%`-wildcard wrapping is constructed in Python and passed as parameter *values*, not interpolated into the query *text*.

### FR-02: `q` Cannot Alter Query Structure
After the fix, no value supplied in `q` may change the number of clauses, tables, or columns referenced by the executed SQL — the query text itself must be a fixed string, with only the bound parameter values varying per request.

### FR-03: HTML-Escaped Reflection of `q`
The `q` value embedded in the `<h2>Search results for: ...</h2>` heading must be passed through `html.escape()` before being embedded in the response HTML.

### FR-04: HTML-Escaped Result Rows
Each result row's `username` and `email` fields, as embedded into the `<li>{username} ({email})</li>` fragments, must be passed through `html.escape()` before being embedded in the response HTML.

### FR-05: Generic Error Response
The `except Exception:` handler must return an `HTMLResponse` with `status_code=500` whose body contains a fixed, generic error message (e.g. `<p>Search error. Please try again.</p>`) and no interpolated exception object, exception message, or stack trace of any kind.

### FR-06: Response Shape Preserved
The route continues to accept `GET /search?q=...`, continues to default `q` to `""` when absent, and continues to return an `HTMLResponse` HTML fragment (an `<h2>` heading followed by a `<ul>` of `<li>` rows) — no change to the route's method, path, query-parameter name, or response content type.

### FR-07: No Unrelated Vulnerability Fixes
This change must not modify `auth_service.py`'s already-parameterized `signup()`/`login()` queries (VULN-1), must not escape the `/welcome` `{{username}}` substitution further than its existing VULN-2 fix, must not add authentication to `/download/db` (VULN-6, already fixed independently), and must not add rate-limiting or CSRF middleware (VULN-7/VULN-8).

---

## 5. Non-Functional Requirements

### NFR-01: No String-Built SQL for User Input
No raw value derived from `q` may be interpolated, formatted, or concatenated into SQL statement text in `search_user()`. It must be passed exclusively via the parameter-binding tuple argument to `conn.execute()`.

### NFR-02: Consistent with Existing Remediation Style
The parameterized query must use the same `sqlite3` `?`-placeholder + tuple-binding pattern already established by the VULN-1 fix in `auth_service.py` (per `.claude/specs/sql-injection-fix.md`), and the HTML-escaping must use the same `html.escape()` standard-library call already used by the VULN-2 fix in `welcome_page()` — no new escaping/templating library or SQL-building abstraction is introduced.

### NFR-03: No New Dependencies
`sqlite3` parameter binding and `html.escape()` are both already available (the former via the standard library already in use for `get_db()`, the latter already imported at the top of `auth.py`). No new package is added to `backend/pyproject.toml` or the root `pyproject.toml`.

### NFR-04: No Information Leakage on Error
No response from `/search`, under any input or failure condition, may contain a Python exception's `str()` representation, exception class name, file path, line number, or traceback fragment.

### NFR-05: Minimal Diff
The change is limited to `search_user()`'s function body in `auth.py`; no other function, route, or file is modified.

---

## 6. Success Paths

**SP-01 — Normal search with matches**: `q` matches one or more existing usernames/emails → parameterized `SELECT` returns the matching rows → response is `200` with an `<h2>` heading (escaped `q`) followed by `<li>` entries for each match (escaped `username`/`email`).

**SP-02 — Normal search with no matches**: `q` matches no existing username or email → parameterized `SELECT` returns zero rows → response is `200` with the `<h2>` heading and an empty `<ul></ul>` — a valid, well-formed HTML fragment, not an error.

**SP-03 — Empty query parameter**: `q` is omitted or empty → the route's existing default (`q: str = ""`) applies; the parameterized query executes with `%%` as both bound wildcard values, matching all rows exactly as it did pre-fix for an empty `q` (no behavior change to the empty-query case beyond parameterization/escaping) — see EC-05 for the exact `LIKE '%%'` matching-everything nuance carried over from the current implementation.

**SP-04 — Search terms containing characters that previously required escaping**: a `q` value containing `'`, `"`, `%`, or `_` is submitted. Because the value is bound as a parameter rather than concatenated into SQL text, no manual SQL escaping is needed; the value is matched literally (subject to SQL `LIKE` wildcard semantics for `%`/`_` within the parameter value itself) without altering query structure.

---

## 7. Edge Cases

**EC-01 — Reflected XSS payload in `q`**: `q=<script>alert(1)</script>` (or `q=<img src=x onerror=alert(1)>`) is submitted. The heading renders the payload as HTML-escaped literal text (e.g. `&lt;script&gt;alert(1)&lt;/script&gt;`) — the script does not execute in a browser rendering the response.

**EC-02 — SQL injection / authentication-bypass-style payload in `q`**: `q=' OR '1'='1` is submitted. Because the value is bound as a parameter, it is treated as a literal substring to match within `LIKE '%...%'`, not as SQL syntax — the query does not return every row in the table as a side effect of the payload altering the `WHERE` clause, and no SQL error occurs.

**EC-03 — XSS payload embedded in a stored username/email**: if a user record exists whose `username` or `email` contains HTML/script markup (e.g. a `username` that was stored before the VULN-2 fix, or via any other path), that value must still render as escaped, inert text when it appears in `/search` results — the escaping applies to result-row fields regardless of how the payload originally entered the database.

**EC-04 — Search matching zero results**: a `q` value with no matching username or email (e.g. a random string not present in the table) renders a valid `200` response with an empty result list — not an error, not a `500`.

**EC-05 — Search triggering a database error**: if the underlying query execution raises an exception (e.g. a locked or corrupted database file), the response is `500` with the fixed generic error message from FR-05 — the response body contains no exception message, class name, or traceback text, in contrast to the pre-fix `f"<p>Search error: {e}</p>"` behavior.

**EC-06 — Quotes, comments, and operators in `q`**: inputs containing single quotes (`'`), SQL comment sequences (`--`, `/* */`), boolean operators (`OR`, `AND`), or `UNION SELECT` fragments, submitted as `q`, must not alter query semantics, return unexpected rows, or change the number of columns/tables referenced — the query text is fixed regardless of parameter content.

---

## 8. Acceptance Criteria

**AC-01**: Given the source of `search_user()`, when reviewed, then the `SELECT` query uses `?` placeholders for both the username and email `LIKE` comparisons, with values passed via a bound parameter tuple to `conn.execute()`, not string concatenation or f-string/`.format()` interpolation.

**AC-02**: Given a reflected-XSS payload (`q=<script>alert(1)</script>`) submitted to `GET /search`, when the response is inspected, then the payload appears in the HTML body only in HTML-escaped form (e.g. `&lt;script&gt;`), and no unescaped `<script>` tag is present anywhere in the response.

**AC-03**: Given a SQL-injection-style payload (`q=' OR '1'='1`) submitted to `GET /search`, when the response is inspected, then the response does not return every row in the `users` table as a result of the payload altering query structure, and no `500` or SQL exception occurs solely due to this payload.

**AC-04**: Given a `q` value with zero matching rows, when `GET /search` is requested, then the response is `200` with a well-formed HTML fragment containing an empty result list (no error).

**AC-05**: Given any condition that causes an exception inside `search_user()`, when the response is inspected, then the response body contains no Python exception message, class name, file path, or traceback fragment — only the fixed generic error text, with `status_code=500`.

**AC-06**: Given a normal, non-attack search that matches existing users, when `GET /search?q=...` is requested, then the response still returns `200` with the matching rows rendered in the same `<h2>...</h2><ul>...</ul>` structure as before the fix (content now escaped, structure unchanged).

**AC-07**: Given `backend/app/services/auth_service.py`, when compared to its state before this fix, then it is byte-for-byte unchanged — the VULN-1 remediation is untouched by this document.

**AC-08**: Vulnerability #3 (Reflected XSS, plus its bundled SQL Injection and exception-leakage issues in `/search`) is considered fixed.

**AC-09**: Vulnerabilities #2, #6, #7, #8 remain intentionally unchanged by this document.

---

## 9. Test Cases

| ID | Scenario | Precondition | Expected Result |
|---|---|---|---|
| TC-01 | Reflected XSS payload does not execute | None | `GET /search?q=<script>alert(1)</script>` → `200`; response body contains `&lt;script&gt;alert(1)&lt;/script&gt;` (escaped), no raw `<script>` tag present |
| TC-02 | `<img onerror>` payload does not execute | None | `GET /search?q=<img src=x onerror=alert(1)>` → `200`; response body contains the payload HTML-escaped, no live `onerror` attribute in unescaped form |
| TC-03 | SQL injection payload does not return all users / does not error | At least one real user exists in the database | `GET /search?q=' OR '1'='1` → `200`; response does not list every user in the table, and no `500`/SQL error occurs |
| TC-04 | Zero-result search renders correctly | `q` does not match any existing username or email | `GET /search?q=zzz_no_such_user_zzz` → `200`; response contains the heading and an empty `<ul></ul>`, no error |
| TC-05 | Normal search still returns matches | A user with a known username exists | `GET /search?q=<that username>` → `200`; response contains an `<li>` entry with that user's (escaped) username and email |
| TC-06 | Stored XSS payload in a username still renders escaped in search results | A user record exists whose `username`/`email` contains markup (e.g. `<b>test</b>`) | `GET /search?q=<matching term>` → `200`; the markup appears HTML-escaped in the `<li>` entry, not as live HTML |
| TC-07 | Database error yields generic message, no leakage | A condition causing `conn.execute(...)` or `fetchall()` to raise (e.g. simulated DB unavailability) | Response is `500`; body contains only the fixed generic error text — no exception message, class name, or traceback |
| TC-08 | Empty `q` parameter | None | `GET /search` (no `q`) → `200`; behaves per the existing default-`q=""` matching behavior, now via a parameterized query, with all reflected content escaped |
| TC-09 | `auth_service.py` untouched | None | `git diff -- backend/app/services/auth_service.py` (pre- vs. post-fix) shows no changes |

---

## 10. Verification Steps

1. Start the application from the project root:
   ```
   uv run backend/app/main.py
   ```
   Confirm it is listening at `http://localhost:3001`.

2. **Reflected XSS is neutralized (TC-01, AC-02):**
   ```
   curl -s "http://localhost:3001/search?q=<script>alert(1)</script>"
   ```
   Expected: response body contains `&lt;script&gt;alert(1)&lt;/script&gt;`; no literal `<script>` tag appears anywhere in the body.

3. **`<img onerror>` variant (TC-02):**
   ```
   curl -s "http://localhost:3001/search?q=<img src=x onerror=alert(1)>"
   ```
   Expected: the payload appears HTML-escaped (`&lt;img src=x onerror=alert(1)&gt;`), not as a live `<img>` tag.

4. **SQL injection no longer returns all rows (TC-03, AC-03):**
   ```
   curl -s "http://localhost:3001/search?q=' OR '1'='1"
   ```
   Expected: `200` response; the result list reflects a literal (likely empty or near-empty) substring match, not every user in the database; no `500`/stack trace.

5. **Zero-result search (TC-04, AC-04):**
   ```
   curl -s "http://localhost:3001/search?q=zzz_no_such_user_zzz"
   ```
   Expected: `200` with an empty `<ul></ul>`.

6. **Normal search still works (TC-05, AC-06):**
   - Register a user via `http://localhost:3001/signup` with a known username, e.g. `verifyuser`.
   - Request:
     ```
     curl -s "http://localhost:3001/search?q=verifyuser"
     ```
   Expected: `200` with an `<li>` entry containing `verifyuser` and its email.

7. **Stored markup in a username renders escaped (TC-06):**
   - If a test account with markup in its username/email is available, search for a substring that matches it and confirm the markup appears escaped in the `<li>` output, not as live HTML.

8. **Generic error on failure (TC-07, AC-05, NFR-04):**
   - Simulate a search-time failure (e.g. temporarily rename/lock the SQLite file, if feasible in the test environment) and confirm the response is `500` with only the fixed generic message — no exception text, class name, or traceback in the body.

9. **Source-level parameterization check (AC-01):**
   Inspect `backend/app/api/routes/auth.py` and confirm `search_user()`'s query uses `?` placeholders with a bound parameter tuple, not string concatenation.

10. **`auth_service.py` untouched (AC-07, TC-09):**
    ```
    git diff -- backend/app/services/auth_service.py
    ```
    Expected: no output (no changes).

11. **Other vulnerabilities unaffected (AC-09):**
    ```
    curl -i http://localhost:3001/download/db
    ```
    Expected: unauthenticated request redirects to `/login` (VULN-6 remediation, unchanged by this fix).
    ```
    curl -i http://localhost:3001/welcome
    ```
    Expected: unauthenticated request redirects to `/login` (VULN-2/session behavior unchanged by this fix).
