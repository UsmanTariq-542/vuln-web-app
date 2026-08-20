# Implementation Plan — SQL Injection Remediation (VULN-1)

**Version:** 1.0.0
**Source Spec:** `.claude/specs/sql-injection-fix.md`
**Companion Documents:** `docs/TDD.md`, `.claude/specs/bcrypt-password-hashing.md`

---

## Phase 0 — Preconditions

- Confirm `backend/app/services/auth_service.py` is in its documented `v0.1.1` state: `signup()`'s `INSERT` and `login()`'s `SELECT` are built via string concatenation (per `docs/TDD.md` §3.1.3 and §4.1, row 1), and `login()` already calls `verify_password()` from `backend/app/core/security.py` after fetching the row by `username` (the `v0.1.1` bcrypt remediation).
- Confirm `backend/app/core/security.py` is in its documented `v0.1.1` state (`hash_password()`/`verify_password()` using bcrypt, work factor 12) and is not expected to change in any later phase.
- Confirm `backend/pyproject.toml` and the root `pyproject.toml` list `bcrypt>=4.0.0` and do **not** need any DB-driver or query-builder addition — `sqlite3` (Python standard library, already imported in `auth_service.py` and `db/session.py`) natively supports parameterized queries via `conn.execute(query, params)`. **No new dependency is required in this plan.**

---

## Phase 1 — `auth_service.signup()`: Parameterize the `INSERT`

**File:** `backend/app/services/auth_service.py`

**Current (vulnerable) construction:**
```python
query = (
    "INSERT INTO users (username, email, password) VALUES ('"
    + username + "', '" + email + "', '" + hashed + "')"
)
conn.execute(query)
```

**Target construction:**
```python
query = "INSERT INTO users (username, email, password) VALUES (?, ?, ?)"
conn.execute(query, (username, email, hashed))
```

**Details:**
- Replace the concatenated query string with a fixed literal containing three `?` placeholders, in the same column order (`username, email, password`) as today.
- Pass `username`, `email`, `hashed` as a 3-tuple positional-parameter argument to `conn.execute()`. `hashed` is the return value of `hash_password(password)`, unchanged from `v0.1.1`.
- Do not alter the surrounding `try/except sqlite3.IntegrityError` block, the `conn.commit()`/`conn.close()` calls, the `finally` structure, or the `RedirectResponse`/`HTMLResponse` return values — only the two lines building/executing the query change.
- No change to `hash_password()` or where it is called; `security.py` is not touched in this phase.

**Corresponds to:** spec FR-02, NFR-01, NFR-03, NFR-04.

---

## Phase 2 — `auth_service.login()`: Parameterize the `SELECT`

**File:** `backend/app/services/auth_service.py`

**Current (vulnerable) construction:**
```python
query = "SELECT * FROM users WHERE username = '" + username + "'"
row = conn.execute(query).fetchone()
```

**Target construction:**
```python
query = "SELECT * FROM users WHERE username = ?"
row = conn.execute(query, (username,)).fetchone()
```

**Details:**
- Replace the concatenated `WHERE` clause with a fixed literal containing one `?` placeholder for `username`.
- Pass `username` as a 1-tuple positional-parameter argument to `conn.execute()`.
- No other line in `login()` changes: the `if not username or not password` guard, `conn.close()`, the `if row is None or not verify_password(password, row["password"])` check, session population (`request.session["user_id"|"username"|"email"]`), and the `JSONResponse` returns are all preserved exactly as in `v0.1.1`.

**Corresponds to:** spec FR-01, FR-03, NFR-01, NFR-03, NFR-04.

---

## Phase 3 — Confirm `verify_password()` Flow Is Unchanged

This phase is a **verification-only** step; it modifies no code.

- Confirm `login()` still: (1) fetches the row using the new parameterized `SELECT` by `username` alone (no password/hash in the query), (2) if a row is found, calls `verify_password(password, row["password"])` — imported unchanged from `backend/app/core/security.py` — to perform the bcrypt comparison in Python, and (3) returns the identical `401` payload (`{"success": False, "error": "Invalid username or password."}`) whether the row is missing or `verify_password()` returns `False`.
- Confirm `backend/app/core/security.py` is **not edited** in this plan — no phase touches `hash_password()`, `verify_password()`, `BCRYPT_ROUNDS`, or the `import bcrypt` line. This satisfies spec FR-04, FR-05, EC-05, EC-06, AC-09.
- Confirm `signup()` still calls `hash_password(password)` exactly as before Phase 1; only the subsequent `INSERT` execution changed.

**Corresponds to:** spec FR-04, FR-05, EC-05, EC-06, AC-09.

---

## Phase 4 — Confirm Out-of-Scope Surfaces Are Untouched

This phase is a **verification-only** step; it modifies no code.

- Confirm `backend/app/api/routes/auth.py` is not modified: `/search` (VULN-3, including its own string-concatenated `SELECT`) and `/download/db` (VULN-6) remain exactly as in `v0.1.1`.
- Confirm `backend/app/main.py` (`SECRET_KEY`, VULN-4), `frontend/**` (VULN-2's `{{username}}` substitution point in `dashboard.html` rendering logic lives in `auth.py`, not touched), and the absence of rate-limiting/CSRF middleware (VULN-7/VULN-8) are all unmodified.
- Confirm `backend/app/db/session.py` is unmodified — no schema change (`users` table definition stays as-is).
- Confirm no dependency is added to `backend/pyproject.toml` or the root `pyproject.toml`.

**Corresponds to:** spec FR-06, AC-08, Affected Files §3 ("Inspected but must NOT be modified").

---

## Phase 5 — Manual Verification (per spec §10)

Run these after Phases 1–2 are implemented, using the exact commands and endpoint from the spec.

1. **Start the app:**
   ```
   cd backend && uv sync
   uv run backend/app/main.py
   ```
   Serves at `http://localhost:3001`; login endpoint is `POST http://localhost:3001/login` (form-encoded `username`, `password`).

2. **Valid login (TC-01):** register a test account via `/signup`, then:
   ```
   curl -i -c cookies.txt -X POST http://localhost:3001/login \
     -d "username=<registered-username>" \
     -d "password=<correct-password>"
   ```
   Expect `200` and `{"success": true, "redirect": "/welcome"}`.

3. **Invalid login — wrong password (TC-02):**
   ```
   curl -i -X POST http://localhost:3001/login \
     -d "username=<registered-username>" \
     -d "password=wrong-password"
   ```
   Expect `401` with the standard invalid-credentials error.

4. **Invalid login — nonexistent username (TC-03):**
   ```
   curl -i -X POST http://localhost:3001/login \
     -d "username=does-not-exist" \
     -d "password=anything"
   ```
   Expect `401` with the standard invalid-credentials error.

5. **SQL injection via username — authentication-bypass payload (TC-04/TC-08, AC-03):**
   ```
   curl -i -X POST http://localhost:3001/login \
     --data-urlencode "username=' OR '1'='1' --" \
     --data-urlencode "password=anything"
   ```
   Expect `401`, valid JSON body, no `500`, no stack trace in the response or server console.

6. **SQL comment/operator-based variant (TC-07):**
   ```
   curl -i -X POST http://localhost:3001/login \
     --data-urlencode "username=admin'--" \
     --data-urlencode "password=anything"
   ```
   Expect `401`, no `500`.

7. **SQL injection via password (TC-05):**
   ```
   curl -i -X POST http://localhost:3001/login \
     -d "username=<registered-username>" \
     --data-urlencode "password=' OR '1'='1' --"
   ```
   Expect `401` (payload never reaches SQL; fails bcrypt verification as a literal string).

8. **Username with a single quote — signup then login (TC-06):**
   ```
   curl -i -X POST http://localhost:3001/signup \
     --data-urlencode "username=O'Brien" \
     -d "email=obrien@example.com" \
     -d "password=SomePassword123"
   curl -i -c cookies2.txt -X POST http://localhost:3001/login \
     --data-urlencode "username=O'Brien" \
     -d "password=SomePassword123"
   ```
   Expect signup `302` to `/login`, then login `200` with `{"success": true, "redirect": "/welcome"}`.

9. **Source-level confirmation (AC-01/AC-02):** inspect `backend/app/services/auth_service.py` — both queries must use `?` placeholders with bound parameter tuples, no string concatenation remaining.

10. **`security.py` unmodified (AC-09):**
    ```
    git diff v0.1.1 -- backend/app/core/security.py
    ```
    Expect no output.

11. **Optional test suite:**
    ```
    cd backend && uv run --extra dev pytest
    ```

---

## Summary of File Changes

| File | Change | Phase |
|---|---|---|
| `backend/app/services/auth_service.py` | `signup()` `INSERT` → parameterized (`?` + tuple) | 1 |
| `backend/app/services/auth_service.py` | `login()` `SELECT` → parameterized (`?` + tuple) | 2 |
| `backend/app/core/security.py` | None (verified unchanged) | 3 |
| `backend/app/api/routes/auth.py` | None (verified unchanged) | 4 |
| `backend/app/db/session.py` | None (verified unchanged) | 4 |
| `backend/pyproject.toml` | None (no new dependency) | 0, 4 |
| `pyproject.toml` (root) | None (no new dependency) | 0, 4 |
