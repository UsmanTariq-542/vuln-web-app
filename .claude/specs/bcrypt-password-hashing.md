# Software Specification Document (Remediation Addendum)

## Vulnerable Web Application — Bcrypt Password Hashing

**Version:** 1.0.0
**Companion Documents:** `docs/PRD.md`, `docs/TDD.md`, `.claude/specs/app-foundation.md`

---

## 1. Overview / Purpose

This document specifies the remediation of **VULN-5 (Weak Password Storage)** in the baseline application (`v0.1.0`). The baseline hashes passwords with unsalted MD5 (`backend/app/core/security.py`), a fast, collision-prone digest with no work factor — trivially reversible via rainbow tables or brute force. This addendum replaces that scheme with **bcrypt** (work factor ≥ 12), a slow, salted, adaptive hash purpose-built for password storage.

Because the baseline's `login()` matches the password hash **inside the SQL `WHERE` clause**, and bcrypt embeds a per-hash random salt (so the same plaintext never produces the same hash twice), a SQL equality comparison against a bcrypt hash can never match. This addendum therefore also specifies the minimal, necessary change to `auth_service.login()`: fetch the user row by username alone, then verify the password in Python via `verify_password()`. This is a **consequence of the hashing algorithm change**, not a remediation of VULN-1 (SQL Injection), which remains untouched and unfixed.

---

## 2. Scope & Non-Goals

### In Scope
- **VULN-5 — Weak Password Storage**: replace `hashlib.md5()` with `bcrypt` (work factor ≥ 12) in `backend/app/core/security.py`.
- The minimal change to `auth_service.login()` required to make bcrypt verification possible (moving password comparison from SQL to Python).
- Adding `bcrypt` as a dependency in both `backend/pyproject.toml` and the root `pyproject.toml`.
- A migration note covering the fact that pre-existing MD5-hashed accounts cannot authenticate post-fix.

### Non-Goals (remain intentionally unfixed)
The following 7 vulnerabilities are explicitly **out of scope** and must not be altered by this change:

| # | Vulnerability | Status |
|---|---|---|
| 1 | SQL Injection (`auth_service.py` string concatenation) | **Untouched.** The `INSERT` in `signup()` and the username-lookup `SELECT` in `login()` remain built via string concatenation, no parameterization. |
| 2 | Stored XSS (`/welcome` `{{username}}` substitution) | Untouched. |
| 3 | Reflected XSS (`/search` `q` param, result rows, exception text) | Untouched. |
| 4 | Session Hijacking (hardcoded `SECRET_KEY`) | Untouched. |
| 6 | Exposed Database (`GET /download/db`) | Untouched. |
| 7 | No Rate Limiting | Untouched. |
| 8 | CSRF | Untouched. |

This spec closes **vulnerability #5 only**. No parameterized queries, no escaping, no `SECRET_KEY` change, no auth on `/download/db`, no rate-limiting or CSRF middleware may be introduced as part of this work.

---

## 3. Affected Files

- `backend/app/core/security.py` — hashing/verification implementation.
- `backend/app/services/auth_service.py` — `login()` password-comparison logic only; `signup()`'s SQL construction is unaffected (it already just inserts whatever `hash_password()` returns).
- `backend/pyproject.toml` — add `bcrypt` dependency.
- `pyproject.toml` (root) — add `bcrypt` dependency.

---

## 4. Functional Requirements

### FR-01: Bcrypt Hash Generation
`hash_password(password: str) -> str` must return a bcrypt hash string (produced via `bcrypt.hashpw`) with a work factor (cost/rounds) of **at least 12**, encoded as a UTF-8 string (bcrypt's native output is `bytes`; the function's return type stays `str` to preserve the existing signature/contract).

### FR-02: Bcrypt Hash Verification
`verify_password(plain: str, hashed: str) -> bool` must verify a plaintext password against a bcrypt hash using `bcrypt.checkpw`, returning `True` on match and `False` otherwise.

### FR-03: Legacy Hash Safety
`verify_password()` must wrap the `bcrypt.checkpw` call in a `try/except`. A stored value that is not a valid bcrypt hash (e.g., a 32-character MD5 hex digest left over from the baseline) must cause `verify_password()` to return `False`, not raise an unhandled exception.

### FR-04: Public API Stability
The public functions `hash_password(password)` and `verify_password(plain, hashed)` must keep their existing names, parameter order, and return types (`str` and `bool` respectively) so no caller outside `security.py` needs to change beyond `auth_service.login()` (see FR-05).

### FR-05: Login Comparison Moves to Python
`auth_service.login()` must no longer concatenate the password hash into the SQL `WHERE` clause. Instead:
1. Query for the user row by `username` only (string concatenation retained — VULN-1 is out of scope).
2. If a row is found, call `verify_password(password, row["password"])` in Python.
3. Treat "no row found" and "row found but `verify_password()` returns `False`" identically: `401` with the existing `{"success": False, "error": "Invalid username or password."}` payload. The response must not reveal whether the username exists.

### FR-06: Signup Unaffected in Shape
`signup()` continues to call `hash_password(password)` and insert the result via string concatenation exactly as before; only the *content* of the hash changes (bcrypt instead of MD5), not the SQL construction.

### FR-07: Dependency Declaration
`bcrypt` must be added as a runtime dependency in both `backend/pyproject.toml` (`[project.dependencies]`) and the root `pyproject.toml` (`[project.dependencies]`), matching the existing dependency array style in each file (unpinned lower-bound version specifier, e.g. `bcrypt>=4.0.0`).

---

## 5. Non-Functional Requirements

### NFR-01: Work Factor
Bcrypt cost factor must be **≥ 12**. This is a fixed constant in `security.py`, not configurable via environment variable (consistent with the project's existing "no env-sourced security config" posture for `SECRET_KEY`).

### NFR-02: No Behavior Change to Unrelated Flows
Signup's response shapes (redirect on success, `HTMLResponse` 400 on duplicate/missing fields) and login's response shapes (`JSONResponse` success/error payloads) must remain byte-for-byte identical in structure to the baseline — only the password-matching mechanism changes.

### NFR-03: No New Route Surface
No new endpoints, migration scripts, or admin tooling are introduced. Migration is handled procedurally (re-registration), not programmatically.

---

## 6. Success Paths

**SP-01 — New user registers and logs in**: a new account is created via `signup()` → `hash_password()` produces a bcrypt hash beginning with `$2b$` → the hash is stored → the user logs in with the same credentials → `login()` fetches the row by username → `verify_password()` returns `True` → session is established as in the baseline → `302`/JSON success as before.

**SP-02 — Two users, same password, different hashes**: two distinct accounts are registered with an identical plaintext password → because bcrypt generates a fresh random salt per call, the two stored hash values differ → both users can independently log in with their shared plaintext password.

---

## 7. Edge Cases

**EC-01 — Legacy MD5 row**: a user row created under the pre-fix baseline (32-char lowercase hex MD5 digest in the `password` column) attempts to log in with their correct original plaintext password. `bcrypt.checkpw` cannot parse a non-bcrypt hash; `verify_password()` must catch the resulting error and return `False`, yielding a normal `401` invalid-credentials response — not a `500`.

**EC-02 — Wrong password against a valid bcrypt hash**: an existing (post-fix) user submits an incorrect password. `verify_password()` returns `False`; `401` as in the baseline.

**EC-03 — Nonexistent username**: `login()` finds no row for the given username. No `verify_password()` call is made; `401` with the same generic error message as EC-02 (indistinguishable from a wrong-password failure).

**EC-04 — Empty/missing credentials**: unchanged from baseline — `username`/`password` required-field check in `login()` runs before any DB query or hash comparison.

**EC-05 — Corrupted/malformed stored hash**: any stored `password` value that isn't a well-formed bcrypt hash (truncated, empty string, non-UTF8-safe bytes) is handled by the same `try/except` as EC-01, returning `False` rather than raising.

---

## 8. Acceptance Criteria

**AC-01**: Given a new registration, when the created row's `password` column is inspected, then its value begins with `$2b$` (or `$2a$`/`$2y$` per the underlying bcrypt implementation's convention) and is not a 32-character hex string.

**AC-02**: Given a freshly registered user, when they log in with correct credentials, then authentication succeeds and the session is populated with `user_id`, `username`, `email`, identical to baseline behavior.

**AC-03**: Given a freshly registered user, when they log in with an incorrect password, then a `401` JSON error is returned and no session is established.

**AC-04**: Given a legacy MD5-hashed row (simulated by directly inserting a 32-char MD5 hex digest into the `password` column), when that user attempts to log in with their correct original plaintext password, then the server returns a `401` JSON error and does **not** raise an unhandled exception or return a `500`.

**AC-05**: Given two users registered with the identical plaintext password, when their stored `password` column values are compared, then the two hash strings are different.

**AC-06**: Given the SQL query construction in `signup()` and `login()`, when reviewed, then it remains string-concatenated (unparameterized) — unchanged from baseline, confirming VULN-1 was not incidentally remediated.

**AC-07**: Given `bcrypt` in both `backend/pyproject.toml` and the root `pyproject.toml`, when dependencies are installed via `uv sync`, then the `bcrypt` package is resolved and importable.

---

## 9. Test Cases

| ID | Scenario | Precondition | Expected Result |
|---|---|---|---|
| TC-01 | New registration produces bcrypt hash | None | `users.password` for the new row starts with `$2b$` (not a 32-char hex string) |
| TC-02 | Successful login post-fix | User registered under the bcrypt scheme | `200`/JSON `{"success": true, "redirect": "/welcome"}`; session populated |
| TC-03 | Failed login — wrong password | User registered under the bcrypt scheme | `401` JSON error; no session established |
| TC-04 | Legacy MD5 row does not crash login | A row exists with a raw MD5 hex digest in `password` (inserted directly, bypassing `signup()`) | `401` JSON error; no `500`; no unhandled exception/stack trace |
| TC-05 | Same password, two users, different hashes | Two accounts registered with identical plaintext passwords | The two stored `password` values differ |
| TC-06 | Login comparison happens in Python, not SQL | User registered under the bcrypt scheme | `login()`'s SQL query contains no `password =` clause; only `username` is used to fetch the row |
| TC-07 | SQLi construction unchanged | None | `signup()`/`login()` source still builds queries via string concatenation, no parameter placeholders |
| TC-08 | Empty credentials still rejected | None | Submitting login with empty username or password returns `401` without querying the DB or calling `verify_password()` |
| TC-09 | Work factor is ≥ 12 | New registration | Hash string's cost segment (e.g. `$2b$12$...`) is `12` or greater |

---

## 10. Verification Steps

1. Install the new dependency:
   ```
   cd backend && uv sync
   ```
2. Start the application from the project root:
   ```
   uv run backend/app/main.py
   ```
3. Register a new account:
   - Navigate to `http://localhost:3001/signup`, submit a unique username/email/password.
4. Inspect the stored hash (confirms AC-01 / TC-01 / TC-09):
   ```
   sqlite3 <path-to-db-file> "SELECT username, password FROM users WHERE username = '<the username used above>';"
   ```
   Confirm the `password` value begins with `$2b$12$` (or higher cost factor).
5. Log in with the same credentials at `http://localhost:3001/login` — confirm redirect to `/welcome` with the correct username displayed (TC-02).
6. Log in again with a deliberately wrong password for the same account — confirm inline `401` error, no redirect (TC-03).
7. Simulate a legacy account and confirm it fails safely (TC-04):
   ```
   sqlite3 <path-to-db-file> "INSERT INTO users (username, email, password) VALUES ('legacyuser', 'legacy@example.com', '5f4dcc3b5aa765d61d8327deb882cf99');"
   ```
   Attempt to log in as `legacyuser` with the plaintext password that hashes to that MD5 digest (`password`). Confirm the server returns a `401` JSON error (not a `500`) and the process does not crash — check server logs for absence of a Python traceback.
8. Register two more accounts with the same plaintext password and confirm their stored hashes differ (TC-05):
   ```
   sqlite3 <path-to-db-file> "SELECT username, password FROM users WHERE username IN ('<user-a>', '<user-b>');"
   ```
9. Confirm VULN-1 remains unremediated (AC-06 / TC-07) by inspecting `backend/app/services/auth_service.py` — both `signup()`'s `INSERT` and `login()`'s username-lookup `SELECT` must still use string concatenation.

---

## 11. Migration Note

Bcrypt hashes and MD5 hashes are not interchangeable, and there is no reverse path from an MD5 digest back to the original plaintext to re-hash it with bcrypt. Consequently:

- **All user accounts created under the pre-fix (MD5) baseline become unable to log in** once this change is deployed — their stored hash will never satisfy `bcrypt.checkpw`, and (per FR-03/EC-01) the failure is a clean `401`, not a crash.
- The remediation path for existing accounts is **re-registration**: affected users must sign up again via `/signup`, which will store a new bcrypt hash under `hash_password()`.
- No automated migration script, forced-reset flow, or dual-hash-scheme transition period is in scope for this addendum. The lab environment's DB is expected to be reset (or accounts re-registered) after this change is applied.
