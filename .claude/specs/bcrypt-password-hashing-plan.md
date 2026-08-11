# Implementation Plan: Bcrypt Password Hashing

## Vulnerable Web Application — Remediation of VULN-5

**Version:** 1.0.0
**Companion Spec:** `.claude/specs/bcrypt-password-hashing.md`

---

## 1. Context

This plan sequences the implementation of `.claude/specs/bcrypt-password-hashing.md`: replacing the baseline's unsalted MD5 password hashing (`backend/app/core/security.py`) with bcrypt (work factor ≥ 12), and the consequent change to `auth_service.login()` needed because bcrypt's per-hash random salt makes SQL-side equality matching on the password impossible.

**This is a documentation-only planning step.** No source file is edited as part of producing this plan. The plan describes *how* the code change will be made in a later step, driven by whatever prompt executes it.

**Scope discipline carried into every phase below:**
- Only `backend/app/core/security.py`, `backend/app/services/auth_service.py`'s `login()`, `backend/pyproject.toml`, and the root `pyproject.toml` are touched.
- `signup()`'s SQL and `login()`'s username-lookup SQL remain string-concatenated — **VULN-1 (SQL Injection) is not remediated by this work.**
- No other vulnerability (#2 Stored XSS, #3 Reflected XSS, #4 Session Hijacking, #6 Exposed DB, #7 No Rate Limiting, #8 CSRF) is touched, weakened, or strengthened.
- No new endpoints, migration scripts, or config flags are introduced.

---

## 2. Phase Overview

| Phase | Deliverable | Files Touched |
|---|---|---|
| 1 | Add `bcrypt` dependency | `backend/pyproject.toml`, `pyproject.toml` |
| 2 | Rewrite `security.py` to use bcrypt | `backend/app/core/security.py` |
| 3 | Move password comparison out of SQL in `login()` | `backend/app/services/auth_service.py` |
| 4 | Verification pass | none (manual test execution only) |

Phases are sequential: Phase 2 depends on Phase 1's import being installed; Phase 3 depends on Phase 2's new `verify_password()` contract; Phase 4 depends on all three being complete.

---

## 3. Phase 1 — Dependency Addition

**Goal:** Make the `bcrypt` package importable in both the backend subproject and the root project, satisfying FR-07/AC-07.

**Changes:**

- `backend/pyproject.toml`: add `"bcrypt>=4.0.0"` to the `dependencies` array (alongside `fastapi`, `uvicorn`, `python-multipart`, `itsdangerous`), preserving the existing unpinned lower-bound style.
- `pyproject.toml` (root): add `"bcrypt>=4.0.0"` to its `dependencies` array (alongside `fastapi`, `itsdangerous`, `python-multipart`, `uvicorn`), keeping the array alphabetically consistent with the existing entries.

**Execution note:** after editing both files, dependency resolution is performed via `cd backend && uv sync` (per spec §10 step 1) — this regenerates `backend/uv.lock`. The plan does not lock the version itself; `uv sync` does.

**Done when:** both `pyproject.toml` files list `bcrypt`, and `uv sync` completes without error, making `import bcrypt` available to `backend/app/core/security.py`.

---

## 4. Phase 2 — Rewrite `backend/app/core/security.py`

**Goal:** Replace the MD5 implementation with bcrypt, satisfying FR-01, FR-02, FR-03, FR-04, NFR-01.

**Current implementation (baseline, to be replaced):**
```python
import hashlib

# VULN-5: Weak Password Storage (intentional).
# MD5 with no salt, no pepper, no key-derivation function. Do not "fix" this here --
# bcrypt/argon2 migration is a later, separate exercise.


def hash_password(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    return hash_password(plain) == hashed
```

**Target implementation:**

```python
import bcrypt

# VULN-5 remediated: bcrypt (work factor 12) replaces unsalted MD5.
# See .claude/specs/bcrypt-password-hashing.md.

BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode(), salt).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False
```

**Design notes carried from the spec:**
- `hash_password()` keeps its `(password: str) -> str` signature (FR-04). `bcrypt.hashpw` returns `bytes`; `.decode()` restores the `str` contract so no caller elsewhere needs to change.
- `bcrypt.gensalt(rounds=BCRYPT_ROUNDS)` is the mechanism for enforcing the ≥12 work factor (NFR-01); the constant is a fixed value in this file, never read from an environment variable, matching the project's existing posture on hardcoded security config (mirrors `SECRET_KEY` in `main.py`).
- `verify_password()` keeps its `(plain: str, hashed: str) -> bool` signature (FR-04).
- The `try/except ValueError` around `bcrypt.checkpw` is the FR-03 legacy-hash guard: `bcrypt.checkpw` raises `ValueError` (via the underlying `_bcrypt` module) when the second argument isn't a validly-formatted bcrypt hash — which is exactly the shape of a leftover 32-character MD5 hex digest. Catching only `ValueError` (not a bare `except:`) is deliberate — it fails safe on the one documented failure mode (malformed hash) without masking unrelated bugs.
- No other function, import, or module-level constant is added. No comment referencing VULN-1 or other out-of-scope vulnerabilities is introduced here.

**Done when:** `hash_password()` returns a string beginning with `$2b$12$...` for any input, and `verify_password()` returns `False` (not an exception) for both a wrong password against a valid bcrypt hash and any non-bcrypt string (e.g. an MD5 digest).

---

## 5. Phase 3 — Move Password Comparison to Python in `auth_service.login()`

**Goal:** Satisfy FR-05 — since bcrypt hashes can't be matched via SQL `=`, fetch by username only and verify in Python, while leaving `signup()` and the SQL-construction style untouched (FR-06, AC-06).

**Current implementation (baseline, to be replaced — `login()` only):**
```python
def login(request: Request, username: str, password: str):
    if not username or not password:
        return JSONResponse({"success": False, "error": "Username and password are required."}, status_code=401)

    hashed = hash_password(password)

    conn = get_db()
    query = (
        "SELECT * FROM users WHERE username = '" + username
        + "' AND password = '" + hashed + "'"
    )
    row = conn.execute(query).fetchone()
    conn.close()

    if row is None:
        return JSONResponse({"success": False, "error": "Invalid username or password."}, status_code=401)

    request.session["user_id"] = row["id"]
    request.session["username"] = row["username"]
    request.session["email"] = row["email"]

    return JSONResponse({"success": True, "redirect": "/welcome"})
```

**Target implementation:**
```python
def login(request: Request, username: str, password: str):
    if not username or not password:
        return JSONResponse({"success": False, "error": "Username and password are required."}, status_code=401)

    conn = get_db()
    query = "SELECT * FROM users WHERE username = '" + username + "'"
    row = conn.execute(query).fetchone()
    conn.close()

    if row is None or not verify_password(password, row["password"]):
        return JSONResponse({"success": False, "error": "Invalid username or password."}, status_code=401)

    request.session["user_id"] = row["id"]
    request.session["username"] = row["username"]
    request.session["email"] = row["email"]

    return JSONResponse({"success": True, "redirect": "/welcome"})
```

**Design notes carried from the spec:**
- The `SELECT` still string-concatenates `username` directly into the query — **this is VULN-1, and it is preserved exactly as-is.** Only the `AND password = '...'` clause is removed; the query is not parameterized or otherwise hardened.
- `hashed = hash_password(password)` is deleted from `login()` — it served the SQL-side comparison that no longer exists. (It stays in `signup()`, unchanged — FR-06.)
- `row is None or not verify_password(...)` is evaluated with short-circuit `or`: `verify_password()` is only called when a row was actually found, so a nonexistent username never reaches `verify_password()` (EC-03) and the response is identical either way — `401` with the same generic message, revealing nothing about whether the username exists (FR-05.3).
- The two-line early-return collapses cleanly into the same `if row is None:` branching shape the baseline already used, so the rest of the function (session population, success response) is untouched byte-for-byte (NFR-02).
- `import` statement in `auth_service.py` already brings in `hash_password` from `app.core.security`; add `verify_password` to that same import line.

**Done when:** `login()`'s SQL query contains no `password =` clause (TC-06); `signup()` is unmodified; a correct-credentials login still succeeds and populates the session identically to baseline; an incorrect password, and a nonexistent username, both yield the same `401` payload.

---

## 6. Phase 4 — Verification

**Goal:** Confirm the implementation satisfies every acceptance criterion and test case in the spec (§8–9) before considering the work done. No code changes occur in this phase — only running the app and inspecting results, per spec §10.

**Steps (mirrors spec §10 exactly):**

1. `cd backend && uv sync` — confirms Phase 1's dependency resolves (AC-07).
2. `uv run backend/app/main.py` — start the app from the project root.
3. Register a new account via `http://localhost:3001/signup`.
4. Inspect the stored hash via `sqlite3 <db-file> "SELECT username, password FROM users WHERE username = '<username>';"` — confirm it begins with `$2b$12$` (AC-01, TC-01, TC-09).
5. Log in with the same credentials at `http://localhost:3001/login` — confirm redirect to `/welcome` with the correct username (AC-02, TC-02).
6. Log in again with a wrong password for the same account — confirm inline `401`, no redirect (AC-03, TC-03).
7. Simulate a legacy MD5 row directly via `sqlite3 <db-file> "INSERT INTO users (username, email, password) VALUES ('legacyuser', 'legacy@example.com', '5f4dcc3b5aa765d61d8327deb882cf99');"`, then attempt to log in as `legacyuser` with `password` — confirm a clean `401` JSON response and no `500`/traceback in server logs (AC-04, TC-04).
8. Register two more accounts with an identical plaintext password; compare their stored `password` values — confirm they differ (AC-05, TC-05).
9. Re-inspect `backend/app/services/auth_service.py` to confirm both `signup()`'s `INSERT` and `login()`'s `SELECT` remain string-concatenated, unparameterized (AC-06, TC-06, TC-07).
10. Submit login with an empty username or password — confirm `401` with no DB query attempted (TC-08 — already covered by the untouched required-field check at the top of `login()`, but re-verify post-change since the function body around it changed).

**Migration note to surface to whoever runs this plan:** per spec §11, any accounts created before this change (MD5 hashes) become unable to log in — there is no automated migration; affected accounts must re-register via `/signup`. If a persistent `vulnerable_app.db` from before this change exists in the working environment, either delete it (per TDD §6.4 — recreated automatically on next startup) or have affected users re-register, before relying on step 5 above.

**Done when:** all 9 test cases (TC-01 through TC-09) and all 7 acceptance criteria (AC-01 through AC-07) pass as described.

---

## 7. Explicit Non-Changes (carried into every phase)

To keep this remediation scoped to VULN-5 only, the following must remain true after all phases:

- `signup()`'s `INSERT` query: still string-concatenated (unchanged).
- `login()`'s `SELECT` query: still string-concatenated on `username` (changed only by removing the `password =` clause).
- `/welcome`'s `{{username}}` substitution in `auth.py`: untouched (VULN-2).
- `/search`'s reflected `q` handling in `auth.py`: untouched (VULN-3).
- `main.py`'s hardcoded `SECRET_KEY = "super-secret-key-12345"`: untouched (VULN-4).
- `/download/db` in `auth.py`: still unauthenticated (VULN-6).
- No rate-limiting middleware added (VULN-7).
- No CSRF tokens or middleware added (VULN-8).
