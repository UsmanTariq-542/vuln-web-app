# Implementation Plan — Session Hijacking Remediation (VULN-4)

**Version:** 1.0.0
**Source Spec:** `.claude/specs/session-hijacking-fix.md`
**Companion Documents:** `docs/PRD.md`, `docs/TDD.md`, `.claude/specs/bcrypt-password-hashing.md`, `.claude/specs/sql-injection-fix.md`

---

## Phase 0 — Preconditions

- Confirm `backend/app/main.py` is in its current state: `SECRET_KEY = "super-secret-key-12345"` (module-level literal), passed as `app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)` with no other keyword arguments — no `https_only`, no `max_age`. `os` is already imported (used for `PORT`); `secrets` is not yet imported.
- Confirm `backend/app/services/auth_service.py`'s `login()` still sets `request.session["user_id"]`, `request.session["username"]`, `request.session["email"]` and that `backend/app/api/routes/auth.py`'s `welcome_page()`/`logout()` still read/clear `request.session` exactly as documented in the spec — these are inspection-only checkpoints, not files this plan will edit.
- Confirm `backend/pyproject.toml` and the root `pyproject.toml` need no new dependency: `os` and `secrets` are both Python standard library, sufficient per spec NFR-05.
- Confirm the repository root `.gitignore` already ignores `.env` and `.env.local` (verified present). No `.env.example` file currently exists.

---

## Phase 1 — `SECRET_KEY` Sourced From Environment Variable

**File:** `backend/app/main.py`

**Current (vulnerable) construction:**
```python
# VULN-4: Session Hijacking (intentional). Hardcoded, guessable secret key --
# do not source this from an environment variable or a random generator.
SECRET_KEY = "super-secret-key-12345"
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
```

**Target construction:**
```python
import secrets

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    print(
        "WARNING: SECRET_KEY environment variable is not set. "
        "Using a randomly generated ephemeral key for this run only; "
        "all sessions will be invalidated on restart.",
        file=sys.stderr,
    )
```

**Details (exact mechanism per spec FR-01):**
- Read the key via `os.environ.get("SECRET_KEY")` (falsy check covers both "unset" and empty-string values).
- **Fallback behavior if unset: do not raise, do not exit.** Generate a random ephemeral key with `secrets.token_hex(32)` (stdlib CSPRNG) and continue starting the app, so `uv run backend/app/main.py` still works out of the box for the educational lab.
- Emit a warning to stderr (via `print(..., file=sys.stderr)`, consistent with a plain-stdlib approach — `sys` is already imported at the top of `main.py`) stating that no `SECRET_KEY` was configured and a random ephemeral key is in use for this run only. Do not log the generated key value itself.
- Add `import secrets` near the existing `import os` in `main.py`. No other new imports are required.
- This satisfies FR-01, NFR-01 (never hardcoded), NFR-05 (stdlib only).

**Corresponds to:** spec FR-01, NFR-01, NFR-05, AC-01.

---

## Phase 2 — `.env` / `.env.example` / `.gitignore` Handling

This phase adds developer-convenience scaffolding so a stable `SECRET_KEY` can be set locally without ever being committed. No source code changes occur in this phase.

- **`.gitignore`:** already lists `.env` and `.env.local` (confirmed in Phase 0) — **no change needed**.
- **`.env.example`** *(new file, repo root)*: add a template showing the expected variable name without a real secret value, e.g.:
  ```
  # Copy to .env and set a real value for local development.
  # Never commit a real SECRET_KEY.
  SECRET_KEY=
  ```
  This file is tracked (not ignored) since it contains no secret — only the variable name as documentation.
- **No `.env`-parsing library is introduced.** `main.py` continues to read `os.environ` directly (per NFR-04's "stay within existing structure" constraint); if a developer wants `.env` file support, they export the variable in their shell before running `uv run backend/app/main.py` (documented in Phase 5 verification), or use a shell/tool that loads `.env` outside the app's own code (e.g. `export $(cat .env | xargs)` or their shell's built-in dotenv support). This avoids adding `python-dotenv` or similar as a new dependency, per NFR-05.
- Confirm no real secret value is ever written into `.env.example`, `main.py`, or any other tracked file.

**Corresponds to:** spec NFR-01, NFR-05, Affected Files §3 ("dependency files ... if a new dependency is required" — none is).

---

## Phase 3 — `SessionMiddleware` Hardening: `https_only=True` and `max_age`

**File:** `backend/app/main.py`

**Target construction (combining with Phase 1's key-sourcing):**
```python
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    https_only=True,
    max_age=1800,
)
```

**Details:**
- Add `https_only=True` as an explicit keyword argument — marks the session cookie `Secure`, so it is not transmitted over plain HTTP. (Spec FR-02, AC-02.)
- Add `max_age=1800` (30 minutes, in seconds) as an explicit keyword argument, replacing Starlette's 14-day default. No sliding/rolling renewal is introduced — a session expires 1800 seconds after issuance regardless of activity. (Spec FR-03, AC-02.)
- Update the module comment above this block to describe the fix (analogous house style to the VULN-1/VULN-5 remediation comments already present elsewhere in the codebase, e.g. `auth_service.py`'s updated VULN-1 comment) instead of the old "do not source this from an environment variable" instruction, which would now be factually wrong.
- No other `SessionMiddleware` parameters are touched — `same_site` and `session_cookie` remain at Starlette defaults (`"lax"` and `"session"` respectively), consistent with spec scope (only `secret_key` sourcing, `https_only`, and `max_age` are in scope).

**Corresponds to:** spec FR-02, FR-03, NFR-03, NFR-04, AC-02.

---

## Phase 4 — Confirm Session Read/Write Logic and Out-of-Scope Surfaces Are Untouched

This phase is a **verification-only** step; it modifies no code.

- Confirm `backend/app/services/auth_service.py` is **not edited**: `login()`'s three `request.session[...] = ...` assignments remain exactly as-is. This file was inspected in Phase 0/READ only.
- Confirm `backend/app/api/routes/auth.py` is **not edited**: `welcome_page()`'s `if "user_id" not in request.session` gate and `{{username}}` substitution, and `logout()`'s `request.session.clear()`, remain exactly as-is. `/search` (VULN-3) and `/download/db` (VULN-6) are untouched.
- Confirm `backend/app/core/security.py` (VULN-5 bcrypt fix) and the parameterized-query lines in `auth_service.py`'s `signup()`/`login()` (VULN-1 fix) are unmodified.
- Confirm no server-side session store, session-ID table, or external session backend (Redis, DB-backed sessions, etc.) is introduced anywhere — sessions remain the existing stateless, `itsdangerous`-signed cookie mechanism.
- Confirm `backend/pyproject.toml` and the root `pyproject.toml` have no new dependency added.

**Corresponds to:** spec FR-04, FR-05, FR-06, Affected Files §3 ("Inspected but must NOT be modified"), AC-07, AC-08.

---

## Phase 5 — Manual Verification (per spec §10)

Run these after Phases 1–3 are implemented, using the exact commands and endpoints from the spec.

1. **Set `SECRET_KEY` and start the app:**
   ```
   export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
   cd backend && uv sync
   cd ..
   uv run backend/app/main.py
   ```
   (PowerShell: `$env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"` before `uv run backend/app/main.py`.)

   Also separately verify the no-env-var fallback path: start the app **without** setting `SECRET_KEY` and confirm the stderr warning from Phase 1 appears before the server begins serving requests.

2. **Endpoints in use:**
   ```
   POST http://localhost:3001/login    (form fields: username, password)
   GET  http://localhost:3001/welcome
   GET  http://localhost:3001/logout
   ```

3. **Valid login → `/welcome` access:**
   ```
   curl -i -c cookies.txt -X POST http://localhost:3001/login \
     -d "username=<a-registered-username>" \
     -d "password=<the-correct-password>"
   curl -i -b cookies.txt http://localhost:3001/welcome
   ```
   Expect `200`/JSON `{"success": true, "redirect": "/welcome"}`, then `200` with the dashboard HTML showing the correct username.

4. **`Set-Cookie` carries `Secure` (confirms `https_only=True`):**
   ```
   curl -i -X POST http://localhost:3001/login \
     -d "username=<a-registered-username>" \
     -d "password=<the-correct-password>" | grep -i "set-cookie"
   ```
   Expect the `Set-Cookie` line to include `Secure` (and `HttpOnly`, Starlette's unchanged default).

5. **Logout revokes access:**
   ```
   curl -i -c cookies.txt -b cookies.txt http://localhost:3001/logout
   curl -i -b cookies.txt http://localhost:3001/welcome
   ```
   Expect the second call to redirect to `/login`, not the dashboard.

6. **Cookie forged with the OLD hardcoded key is rejected:** with the app running under the new key (step 1), forge a session value locally using `itsdangerous` and the old literal key:
   ```python
   # forge_old_cookie.py
   from itsdangerous import TimestampSigner
   import base64, json

   OLD_SECRET_KEY = "super-secret-key-12345"
   data = {"user_id": 1, "username": "admin", "email": "admin@example.com"}
   payload = base64.b64encode(json.dumps(data).encode()).decode()
   signer = TimestampSigner(OLD_SECRET_KEY)
   forged_cookie_value = signer.sign(payload).decode()
   print(forged_cookie_value)
   ```
   ```
   python forge_old_cookie.py
   curl -i --cookie "session=<forged_cookie_value_from_above>" http://localhost:3001/welcome
   ```
   Expect a redirect to `/login`, proving the forged cookie signed with the old key is rejected. (During implementation, confirm the forging script matches the installed Starlette version's actual session-serialization scheme in `starlette/middleware/sessions.py`, since it may use `URLSafeTimedSerializer` rather than a bare `TimestampSigner` — the verification intent is unchanged either way.)

7. **Session expiry after `max_age`:** since waiting 1800 real seconds is impractical for routine manual verification, either (a) temporarily test with a shortened `max_age` to confirm the expiry mechanism functions, then revert to `1800` for the actual implementation, or (b) construct a cookie stamped with a timestamp older than 1800 seconds using the running server's actual key and confirm `/welcome` rejects it (redirect to `/login`).

8. **Old secret literal is gone from tracked source:**
   ```
   grep -rn "super-secret-key-12345" backend/app/main.py
   git grep -n "super-secret-key-12345"
   ```
   Expect no matches in `main.py` or any other application source file (matches only permissible in this plan/spec's own illustrative text, which is not application source).

9. **Bcrypt and SQL-injection fixes remain intact:**
   ```
   git diff v0.1.2 -- backend/app/core/security.py backend/app/services/auth_service.py
   ```
   Expect no output.

10. **Concurrent sessions for two different users:** repeat step 3 with a second registered user and a second cookie jar (`cookies2.txt`); confirm both `/welcome` responses show the correct, distinct username for each and neither cookie grants access to the other's session.

11. **Optional test suite:**
    ```
    cd backend && uv run --extra dev pytest
    ```

---

## Summary of File Changes

| File | Change | Phase |
|---|---|---|
| `backend/app/main.py` | `SECRET_KEY` sourced via `os.environ.get("SECRET_KEY")` with `secrets.token_hex(32)` ephemeral fallback + stderr warning; `import secrets` added | 1 |
| `backend/app/main.py` | `SessionMiddleware` call adds `https_only=True`, `max_age=1800`; stale VULN-4 comment updated | 3 |
| `.env.example` (new, repo root) | Documents the `SECRET_KEY` variable name only, no real value | 2 |
| `.gitignore` | None (already ignores `.env`/`.env.local`) | 0, 2 |
| `backend/app/services/auth_service.py` | None (verified unchanged) | 4 |
| `backend/app/api/routes/auth.py` | None (verified unchanged) | 4 |
| `backend/app/core/security.py` | None (verified unchanged) | 4 |
| `backend/pyproject.toml` | None (no new dependency) | 0, 4 |
| `pyproject.toml` (root) | None (no new dependency) | 0, 4 |
