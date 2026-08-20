# Software Specification Document (Remediation Addendum)

## Vulnerable Web Application — Session Hijacking Remediation

**Version:** 1.0.0
**Companion Documents:** `docs/PRD.md`, `docs/TDD.md`, `.claude/specs/app-foundation.md`, `.claude/specs/bcrypt-password-hashing.md`, `.claude/specs/sql-injection-fix.md`

---

## 1. Overview / Purpose

This document specifies the remediation of **VULN-4 (Session Hijacking)** in `backend/app/main.py`. The application signs its session cookie using Starlette's `SessionMiddleware` with a hardcoded, guessable literal — `SECRET_KEY = "super-secret-key-12345"` — passed as `secret_key=SECRET_KEY`. Because `SessionMiddleware` only *signs* (does not encrypt) the session payload via `itsdangerous`, anyone who knows this key can forge an arbitrary session cookie (any `user_id`/`username`/`email`) and gain authenticated access to `/welcome` without ever logging in.

The same `add_middleware(SessionMiddleware, ...)` call also leaves every other configuration parameter at Starlette's defaults: no `https_only` flag (defaults to `False`, so the cookie is not marked `Secure` and can be sent over plain HTTP), and no `max_age` override (defaults to 14 days, so a stolen or forged cookie remains valid for two weeks with no expiry or idle timeout). These are undocumented weaknesses in the same configuration block, not separately numbered vulnerabilities, and this addendum treats hardening them as part of closing VULN-4 rather than as out-of-scope extras.

This addendum replaces the hardcoded key with one sourced from an environment variable, and adds `https_only=True` and an explicit `max_age` to the same `SessionMiddleware` call. It does not change how session data is structured, read, or written anywhere else in the codebase, and does not introduce a server-side session store — sessions remain stateless, signed cookies, exactly as today, just signed with a non-hardcoded key and expiring sooner.

---

## 2. Scope & Non-Goals

### In Scope
- **VULN-4 — Session Hijacking**: replace the hardcoded `SECRET_KEY` literal in `backend/app/main.py` with a value sourced from an environment variable (with a documented fallback for local dev — see FR-01).
- Hardening the same `SessionMiddleware` configuration call with `https_only=True` and an explicit `max_age` (e.g. 1800 seconds / 30 minutes), since both are undocumented weaknesses in the same block rather than separately numbered vulnerabilities.
- No session-store or session-ID architecture change: sessions remain stateless, signed cookies via `SessionMiddleware`/`itsdangerous`. This addendum does not move to server-side sessions, a session ID + lookup table, Redis, or any other session-storage mechanism.

### Non-Goals (remain intentionally unfixed)
The following 6 vulnerabilities are explicitly **out of scope** and must not be altered by this change:

| # | Vulnerability | Status |
|---|---|---|
| 2 | Stored XSS (`/welcome` `{{username}}` substitution) | Untouched. |
| 3 | Reflected XSS **and** its accompanying SQL Injection in `/search` (`backend/app/api/routes/auth.py`) | Untouched. |
| 6 | Exposed Database (`GET /download/db`) | Untouched. |
| 7 | No Rate Limiting | Untouched. |
| 8 | CSRF | Untouched. |

**Vulnerability #5 (weak password storage), Vulnerability #1 (SQL Injection), and the dark mode toggle are already fixed/implemented** (bcrypt hashing per `.claude/specs/bcrypt-password-hashing.md`, parameterized queries per `.claude/specs/sql-injection-fix.md`, and the presentational theme switch per `.claude/specs/dark-mode-toggle.md`) and are explicitly **outside the scope of this task**. Do not modify `backend/app/core/security.py` or `backend/app/services/auth_service.py`'s query construction, and do not touch any dark-mode-related frontend files.

This spec closes **vulnerability #4 only**, within `backend/app/main.py`'s `SessionMiddleware` configuration. `auth_service.py`'s and `auth.py`'s session read/write logic (`request.session[...]`, `request.session.clear()`) is unaffected — only the key and cookie parameters used to sign/govern that session change.

---

## 3. Affected Files

**To be modified:**
- `backend/app/main.py` — replace the hardcoded `SECRET_KEY` literal with an environment-variable-sourced value, and add `https_only=True` and an explicit `max_age` to the `SessionMiddleware` configuration.
- Dependency files (`backend/pyproject.toml`, root `pyproject.toml`) — only if a new dependency is required to read the environment variable or generate a fallback key. Per NFR-05, the standard library's `os` (for `os.environ.get`) and `secrets` (for a fallback random key) are sufficient, so **no dependency change is expected**; this is listed only in case implementation reveals otherwise.

**Inspected but must NOT be modified:**
- `backend/app/services/auth_service.py` — `login()`'s `request.session["user_id"|"username"|"email"] = ...` assignments; logic is correct as-is and must not change.
- `backend/app/api/routes/auth.py` — `welcome_page()`'s `if "user_id" not in request.session` gate and `{{username}}` substitution, and `logout()`'s `request.session.clear()`; must not change.
- `backend/app/core/security.py` — bcrypt implementation (VULN-5, already fixed); untouched by this task.
- `backend/app/db/session.py` — SQLite connection/schema (unrelated to HTTP session cookies despite the similar module name); untouched.

---

## 4. Functional Requirements

### FR-01: Secret Key Sourced From Environment Variable
`backend/app/main.py` must no longer define `SECRET_KEY` as a hardcoded string literal. Instead, it must be read via `os.environ.get("SECRET_KEY")`. If the `SECRET_KEY` environment variable is **not set**, the application must **not** fail to start and must **not** raise an error — this is an educational lab meant to run with a single `uv run backend/app/main.py` out of the box. Instead, it must fall back to a randomly generated ephemeral key produced with `secrets.token_hex(32)` (or equivalent standard-library CSPRNG-backed generator), generated fresh at process startup, and must emit a clear warning (e.g. via `print()` or the `warnings` module) to stderr/stdout stating that no `SECRET_KEY` was configured and a random ephemeral key is in use for this run only. This fallback key must **not** be logged in full or persisted to disk.

### FR-02: `https_only=True`
The `SessionMiddleware` registration in `main.py` must include `https_only=True` as an explicit keyword argument, so the session cookie is marked `Secure` and is not transmitted over plain HTTP.

### FR-03: Explicit `max_age`
The `SessionMiddleware` registration must include an explicit `max_age` keyword argument set to **1800 seconds (30 minutes)**, replacing Starlette's 14-day default. A session cookie issued at login expires 30 minutes after issuance regardless of activity (no sliding/rolling renewal is introduced by this fix).

### FR-04: Session Read/Write Behavior Preserved
`auth_service.login()` must continue to set `request.session["user_id"]`, `request.session["username"]`, and `request.session["email"]` exactly as today. `auth.py`'s `welcome_page()` must continue to gate on `"user_id" not in request.session` and substitute `request.session["username"]` into the dashboard template exactly as today. `auth.py`'s `logout()` must continue to call `request.session.clear()` exactly as today. None of these three call sites change.

### FR-05: No Server-Side Session Store
This fix must not introduce a session ID, a server-side session table/cache/store, or any change to how session data is serialized. Sessions remain the existing stateless, `itsdangerous`-signed cookie mechanism provided by Starlette's `SessionMiddleware` — only the signing key and the `https_only`/`max_age` parameters change.

### FR-06: No Unrelated Vulnerability Fixes
This change must not escape the `/welcome` `{{username}}` substitution (VULN-2), parameterize or alter the `/search` route (VULN-3), add authentication to `/download/db` (VULN-6), add rate-limiting middleware (VULN-7), or add CSRF tokens/middleware (VULN-8).

---

## 5. Non-Functional Requirements

### NFR-01: No New Hardcoded Secret
The new secret key value must never be a hardcoded literal in source, and must never be committed to the repository (in code, `.env` files checked into git, or any tracked file). If a `.env`-style local file is used to set `SECRET_KEY` for development convenience, it must already be covered by `.gitignore` or be explicitly excluded from version control as part of this change.

### NFR-02: Old-Key Cookies Rejected After Rotation
Once the key is sourced from the environment (or a freshly generated ephemeral fallback) instead of the literal `"super-secret-key-12345"`, any session cookie previously signed with that old literal must fail signature verification and must not be accepted by `SessionMiddleware` — the user is treated as unauthenticated (no session data available), not granted access.

### NFR-03: API Behavior Preserved
Response payloads, status codes, and redirect targets for `login()`, `welcome_page()`, and `logout()` must remain byte-for-byte identical in structure and content to the current (`v0.1.2`) behavior for all non-attack flows. The only externally observable behavior changes are: (a) the session cookie is no longer sent over plain HTTP once `https_only=True` is set, and (b) sessions expire after 30 minutes instead of 14 days.

### NFR-04: Consistent With Existing Configuration Style
The fix must stay within `main.py`'s existing structure — a module-level constant/expression feeding a single `app.add_middleware(SessionMiddleware, ...)` call — rather than introducing a settings/config class, a `.env`-parsing library, or a configuration module, unless such a pattern already exists elsewhere in the repo (it does not, per the READ phase).

### NFR-05: No Unnecessary Dependencies
Reading an environment variable and generating a fallback random key requires only the Python standard library: `os` (already imported in `main.py`, used for `PORT`) and `secrets` (stdlib, not currently imported). No new third-party package is required, and none should be added to `backend/pyproject.toml` or the root `pyproject.toml` for this fix.

---

## 6. Success Paths

**SP-01 — Successful login still sets a valid session cookie and grants access to `/welcome`**: a registered user submits correct credentials to `POST /login` → `login()` sets `request.session["user_id"|"username"|"email"]` as before → the response includes a `Set-Cookie` header for the session, signed with the environment-sourced (or ephemeral fallback) key → a subsequent `GET /welcome` request bearing that cookie succeeds and renders the dashboard with the correct username.

**SP-02 — Logout still clears the session and revokes access to `/welcome`**: an authenticated user visits `GET /logout` → `request.session.clear()` runs as before → a subsequent `GET /welcome` request (even reusing the now-cleared session cookie) is redirected to `/login` because `"user_id"` is no longer in the session.

**SP-03 — A session created after the fix remains valid within the new `max_age` window**: a user logs in and immediately (or any time within 30 minutes) visits `/welcome` → access succeeds, identical to `v0.1.2` behavior, only now bounded by the 30-minute expiry instead of 14 days.

---

## 7. Edge Cases

**EC-01 — Cookie signed with the OLD hardcoded key is rejected after the fix**: a session cookie value that was validly signed under the pre-fix `SECRET_KEY = "super-secret-key-12345"` is presented to `GET /welcome` after the fix is deployed (new key in effect). `itsdangerous`'s signature verification fails against the new key; Starlette's `SessionMiddleware` treats the request as having no valid session (`request.session` is empty); `welcome_page()`'s `"user_id" not in request.session` check is `True`; the response is a redirect to `/login`, not access to the dashboard.

**EC-02 — Manually forged cookie using the old known key is rejected**: an attacker who knows the pre-fix literal `"super-secret-key-12345"` uses `itsdangerous` locally to craft a cookie value encoding an arbitrary `{"user_id": ..., "username": ..., "email": ...}` payload (replicating the pre-fix VULN-4 exploit) and presents it to `GET /welcome` post-fix. Because the running server now signs/verifies with a different key, the forged cookie's signature does not validate; access is denied identically to EC-01.

**EC-03 — Cookie not sent over plain HTTP once `https_only=True` is set**: with `https_only=True`, the browser (or an HTTP client respecting the `Secure` cookie attribute) will not transmit the session cookie over a plain `http://` connection. Because this lab runs locally via `uv run backend/app/main.py` over plain `http://localhost:3001` (per `docs/TDD.md`'s setup instructions and the app's `uvicorn.run(app, host="0.0.0.0", port=port)` call — no TLS is configured), this means the session cookie will not be sent back to the server on subsequent `http://localhost` requests in a real browser once `https_only=True` takes effect, since the browser enforces `Secure` regardless of `localhost` exemptions in cookie transmission for non-HTTPS origins in most contemporary browsers' `fetch()`/cookie-jar behavior for this app's use of `SessionMiddleware`. For local verification, this must be tested with an HTTP client that does **not** enforce the `Secure` attribute op-out (e.g. `curl` with an explicit `-b/-c` cookie jar, or Python's `httpx`/`requests` session objects, which do not strip cookies based on the `Secure` flag the way a real browser does) so that the `Set-Cookie: ...; Secure` attribute's *presence* can be confirmed via response headers, distinct from asserting real-browser transmission behavior. See Verification Steps §10 for the exact approach.

**EC-04 — Session older than `max_age` no longer grants access**: a session cookie issued at login is presented to `GET /welcome` after more than 1800 seconds (30 minutes) have elapsed since issuance. `itsdangerous`'s `TimestampSigner` (used internally by `SessionMiddleware` with `max_age`) rejects the payload as expired; `request.session` is empty; the response redirects to `/login`, identical in shape to EC-01/EC-02.

**EC-05 — Concurrent/multiple simultaneous sessions for different users are unaffected**: two different users log in from two different clients (two different cookie jars) within the same server run. Each receives an independently signed session cookie scoped to their own `user_id`/`username`/`email`. Both can access `/welcome` concurrently and see their own username; one user's session cookie does not grant access to or leak the other's session data. This must continue to hold after the fix exactly as it does today (stateless per-cookie sessions are inherently independent; the fix does not add any shared server-side state that could cross-contaminate sessions).

---

## 8. Acceptance Criteria

**AC-01**: Given `backend/app/main.py`, when reviewed, then `SECRET_KEY` is no longer a hardcoded string literal — its value is sourced via `os.environ.get("SECRET_KEY")`, with a random ephemeral fallback (via `secrets`) and a warning emitted when the environment variable is unset.

**AC-02**: Given the `app.add_middleware(SessionMiddleware, ...)` call in `main.py`, when reviewed, then it includes `https_only=True` and an explicit `max_age=1800` (or the equivalently documented 30-minute value in seconds).

**AC-03**: Given a session cookie forged/signed with the previously hardcoded key value `"super-secret-key-12345"`, when presented to `GET /welcome` after the fix is deployed, then the request is treated as unauthenticated and redirected to `/login` — the forged cookie is rejected.

**AC-04**: Given a legitimately registered user, when they log in via `POST /login` and then visit `GET /welcome` within the `max_age` window, then access succeeds and the dashboard renders with the correct username, exactly as in `v0.1.2`.

**AC-05**: Given an authenticated user, when they visit `GET /logout` and then `GET /welcome`, then they are redirected to `/login`, exactly as in `v0.1.2`.

**AC-06**: Vulnerability #4 (Session Hijacking) is considered fixed.

**AC-07**: Vulnerabilities #2, #3, #6, #7, #8 remain intentionally unchanged.

**AC-08**: Given `backend/app/core/security.py` and the parameterized-query construction in `backend/app/services/auth_service.py`, when compared to their pre-this-task state, then both are byte-for-byte unchanged — the bcrypt fix (#5) and the SQL injection fix (#1) remain fully intact.

---

## 9. Test Cases

| ID | Scenario | Precondition | Expected Result |
|---|---|---|---|
| TC-01 | Normal successful login and access to `/welcome` | User registered under the current (bcrypt + parameterized-query) scheme | `POST /login` returns `200`/JSON `{"success": true, "redirect": "/welcome"}`; subsequent `GET /welcome` with the returned cookie returns `200` and renders the dashboard with the correct username |
| TC-02 | Normal logout and subsequent access denial | User is logged in (valid session cookie held) | `GET /logout` returns a redirect to `/login`; subsequent `GET /welcome` (same cookie) returns a redirect to `/login`, not the dashboard |
| TC-03 | Cookie forged with the OLD hardcoded key is rejected | App is running with the new environment-sourced (or ephemeral fallback) key, not `"super-secret-key-12345"` | A cookie value independently signed with `"super-secret-key-12345"` via `itsdangerous`, encoding an arbitrary `user_id`, presented to `GET /welcome` → redirect to `/login`, not dashboard access |
| TC-04 | Session older than `max_age` is rejected | A valid session cookie was issued more than 1800 seconds ago (simulated via a pre-signed, deliberately old-timestamped cookie or by waiting out the window) | `GET /welcome` with that cookie → redirect to `/login`, not dashboard access |
| TC-05 | New secret key not present in source/version control | None | `grep`-style search for `"super-secret-key-12345"` across tracked source (including `git log -p` / `git grep` history if relevant) returns no matches in `backend/app/main.py` or any other tracked file introduced by this fix; no new literal secret value appears in any tracked file |
| TC-06 | `https_only=True` present in `Set-Cookie` header | App running per Verification Steps | Response headers from `POST /login` include `Set-Cookie: session=...; ...; Secure` (the `Secure` attribute is present) |
| TC-07 | Concurrent sessions for two different users | Two users registered | Both can independently log in and access `/welcome` concurrently, each seeing their own username; neither session grants access to the other's data |

---

## 10. Verification Steps

1. Set the `SECRET_KEY` environment variable for local testing (recommended, so the key is stable across restarts during verification), then install/sync dependencies and start the app from the project root:
   ```
   export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
   cd backend && uv sync
   cd ..
   uv run backend/app/main.py
   ```
   (On Windows PowerShell: `$env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"` before `uv run backend/app/main.py`.)

   To confirm the no-env-var fallback path instead (AC-01's ephemeral-key behavior), start the app without setting `SECRET_KEY` and confirm a warning is printed to the console before the server starts serving requests.

2. The application is served at `http://localhost:3001`. Relevant endpoints:
   ```
   POST http://localhost:3001/login    (form fields: username, password)
   GET  http://localhost:3001/welcome
   GET  http://localhost:3001/logout
   ```

3. Verify normal login → `/welcome` access (TC-01):
   ```
   curl -i -c cookies.txt -X POST http://localhost:3001/login \
     -d "username=<a-registered-username>" \
     -d "password=<the-correct-password>"
   curl -i -b cookies.txt http://localhost:3001/welcome
   ```
   Confirm the first call returns `200`/JSON `{"success": true, "redirect": "/welcome"}`, and the second returns `200` with the dashboard HTML containing the correct username.

4. Verify the `Set-Cookie` header carries `Secure` (TC-06, confirms FR-02/AC-02):
   ```
   curl -i -X POST http://localhost:3001/login \
     -d "username=<a-registered-username>" \
     -d "password=<the-correct-password>" | grep -i "set-cookie"
   ```
   Confirm the `Set-Cookie` line includes `Secure` (and, per Starlette defaults not overridden by this fix, `HttpOnly`).

5. Verify logout revokes access (TC-02):
   ```
   curl -i -c cookies.txt -b cookies.txt http://localhost:3001/logout
   curl -i -b cookies.txt http://localhost:3001/welcome
   ```
   Confirm the second call redirects to `/login`, not the dashboard.

6. Demonstrate that a cookie forged with the OLD hardcoded key is rejected (TC-03 / AC-03 / EC-01 / EC-02). With the app running under the **new** key (per step 1), construct a forged session value locally using `itsdangerous` and the **old** literal key, simulating the pre-fix exploit:
   ```python
   # forge_old_cookie.py — run against the OLD key to simulate a pre-fix-era forged cookie
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
   Confirm the response redirects to `/login` (not the dashboard), proving the forged cookie signed with the old key is rejected by the app now running with the new key.

   (Note: Starlette's `SessionMiddleware` uses `itsdangerous.URLSafeTimedSerializer` in practice, not a bare `TimestampSigner`, to sign a JSON-serialized session dict; the exact serializer construction should be confirmed against the installed Starlette version's `starlette/middleware/sessions.py` source during implementation so the forged-cookie script matches the real signing scheme byte-for-byte. The script above illustrates the verification intent — that a cookie signed under the old key fails against the new key — regardless of the precise serializer internals.)

7. Verify `max_age` expiry (TC-04, EC-04). Since waiting 30 real minutes is impractical for manual verification, either: (a) temporarily verify with a shortened `max_age` value locally to confirm the expiry mechanism works at all (not the final 1800s value), or (b) construct a session cookie with `itsdangerous`/the app's own signing key stamped with a timestamp older than 1800 seconds and confirm it's rejected by `/welcome`. Confirm in both cases the response redirects to `/login`.

8. Confirm the old secret literal is gone from tracked source (TC-05):
   ```
   grep -rn "super-secret-key-12345" backend/app/main.py
   git grep -n "super-secret-key-12345"
   ```
   Both commands should return no matches (or only match this spec file's illustrative examples, not `main.py` or any other application source file).

9. Confirm `backend/app/core/security.py` and the parameterized-query lines in `backend/app/services/auth_service.py` are unmodified from their pre-this-task state (AC-08):
   ```
   git diff v0.1.2 -- backend/app/core/security.py backend/app/services/auth_service.py
   ```
   Expect no output (no changes).

10. Concurrent-session check (TC-07): repeat step 3 with a second registered user and a second cookie jar (e.g. `cookies2.txt`), confirm both `/welcome` responses show the correct, distinct username for each.

11. If the repository's `dev` extra test suite is used, run it from `backend/`:
    ```
    cd backend && uv run --extra dev pytest
    ```
