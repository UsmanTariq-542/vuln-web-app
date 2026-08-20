# Software Specification Document (Remediation Addendum)

## Vulnerable Web Application — CSRF Protection Fix (VULN-8)

**Version:** 1.0.0
**Companion Documents:** `docs/PRD.md`, `docs/TDD.md`, `.claude/specs/app-foundation.md`, `.claude/specs/session-hijacking-fix.md`

---

## 1. Overview / Purpose

Neither `POST /login` nor `POST /signup` currently validates any token proving the request originated from a page the server itself rendered — this is VULN-8, CSRF. A malicious page (hosted anywhere) can trigger a full, unmodified `<form>` POST to `/signup` (creating an attacker-controlled account under the victim's browser context, or worse, be crafted against any future state-changing endpoint that reuses this pattern) or drive a cross-origin `fetch()`/form submission against `/login`, since the browser will happily attach the user's cookies to either. This document specifies the remediation: a session-stored, per-session CSRF token, generated when `GET /login` or `GET /signup` is rendered, embedded in that page's markup, and required — and validated via constant-time comparison — on the corresponding `POST /login`/`POST /signup` submission. A request missing the token, or presenting one that doesn't match the session's stored value, is rejected with `403` before any authentication or account-creation logic runs.

---

## 2. Scope & Non-Goals

**In scope:** This document closes **VULN-8 only**. It adds:
1. A new `backend/app/core/csrf.py` module providing token generation/verification helpers, using Python's standard-library `secrets.token_hex` and `secrets.compare_digest` — no new dependency.
2. Token generation and injection into `GET /login`'s and `GET /signup`'s rendered HTML.
3. Token validation on `POST /login` and `POST /signup`, rejecting with `403` on a missing or mismatched token.

**Out of scope / explicitly not touched:**

- **VULN-2** (Stored XSS) — already remediated per `.claude/specs/stored-xss-fix.md`. Not touched by this document.
- **VULN-3** (Reflected XSS / SQL Injection / exception leakage in `/search`) — already remediated per `.claude/specs/reflected-xss-fix.md`. Not touched by this document.
- **VULN-6** (Exposed Database) — already remediated per `.claude/specs/exposed-database-fix.md`. Not touched by this document.
- **VULN-7** (No Rate Limiting) — already remediated per `.claude/specs/rate-limiting-fix.md`. Not touched by this document; the `@limiter.limit("5/minute")` decorators on `login_post()`/`signup_post()` remain exactly as they are.
- **VULN-1, VULN-4, VULN-5** — already remediated in prior work, unrelated to this fix, and not touched by this document.

**`/logout` is out of scope for token validation, and its underlying design is not changed by this spec:** `GET /logout` clears the session as a side effect of a `GET` request — a state-changing action bound to a safe HTTP method. This is itself a pre-existing design choice from the `v0.1.0` baseline (`app-foundation.md` §3.4), independent of VULN-8, and this spec does not change it: `/logout` is not decorated with CSRF validation, does not gain a token requirement, and its route signature/behavior are entirely untouched. (A cross-site request forcing an unwanted logout is a low-severity nuisance, not a credential-theft or account-takeover primitive, and "logout as GET" is a separate, pre-existing concern this fix does not attempt to address — reclassifying `/logout` as a `POST`-only, token-protected action would be a different, larger change requiring its own spec.) `GET /welcome`, `GET /search`, and `GET /download/db` are likewise untouched — none of them are state-changing POST endpoints and none are in scope.

**No global CSRF middleware:** This fix does not add a blanket CSRF-protection middleware applied to all routes. It adds token generation to two specific `GET` routes and token validation to their two corresponding `POST` routes only, matching the narrow, route-scoped pattern already established by the VULN-7 rate-limiting fix (decorators/checks on the two auth-submission routes, not a global mechanism).

---

## 3. Affected Files

| File | Change |
|---|---|
| `backend/app/core/csrf.py` (**new**) | Token generation (`generate_csrf_token()`) and constant-time verification (`verify_csrf_token(session_token, submitted_token)`) helpers, built on `secrets.token_hex` / `secrets.compare_digest`. |
| `backend/app/api/routes/auth.py` | `signup_page()`/`login_page()` generate-and-inject a token into rendered HTML if the session doesn't already have one; `signup_post()`/`login_post()` validate the submitted token before delegating to `auth_service`. |
| `frontend/templates/signup.html` | Gains a hidden `<input type="hidden" name="csrf_token" value="{{csrf_token}}">` inside `#signup-form`, so the browser's native form POST includes it automatically. |
| `frontend/templates/login.html` | Gains a `data-csrf-token="{{csrf_token}}"` attribute on a container element (e.g. the `#login-form` element itself), which the existing inline `fetch()`-submission script reads and includes in the `FormData`/JSON body it sends to `POST /login`. |

**Inspected but must NOT be modified:**

- `backend/app/services/auth_service.py` — `signup()`/`login()` business logic (VULN-1/VULN-5 remediated); CSRF validation happens in the route layer (`auth.py`), before `auth_service` functions are called, so their signatures and internal logic are unchanged.
- `backend/app/main.py` — `SessionMiddleware` registration (VULN-4 remediated) and the `slowapi` `Limiter`/`RateLimitExceeded` wiring (VULN-7 remediated) are both untouched; the CSRF token is stored in the existing `request.session` dict, requiring no new middleware or session-store change.
- `backend/app/core/security.py` — bcrypt hashing; unrelated to this fix.
- `backend/app/db/session.py` — SQLite connection/schema; unrelated to this fix, no schema change.
- `frontend/templates/dashboard.html` — no protected `POST` route exists on the dashboard; out of scope.
- No new dependency is added to `backend/pyproject.toml` or the root `pyproject.toml` — `secrets` is a Python standard-library module already imported in `main.py`.

---

## 4. Functional Requirements

### FR-01: CSRF Helper Module
`backend/app/core/csrf.py` must provide:
- `generate_csrf_token() -> str`: returns a new random token via `secrets.token_hex(32)` (or equivalent strength).
- `verify_csrf_token(session_token: str | None, submitted_token: str | None) -> bool`: returns `True` only if both values are present (non-`None`, non-empty) and match via `secrets.compare_digest`, and `False` in every other case (either value missing, or a length/content mismatch) — never raising on `None` input.

### FR-02: Token Generated on `GET /login` and `GET /signup`
`login_page()` and `signup_page()` must each: if `"csrf_token"` is not already present in `request.session`, generate one via `generate_csrf_token()` and store it as `request.session["csrf_token"]`; otherwise reuse the existing session value. Both routes gain a `request: Request` parameter to access the session (`login_page()` currently has none; `signup_page()` currently has none).

### FR-03: Token Injected into Signup's Rendered HTML
`signup_page()`'s response HTML must contain a hidden form field carrying the session's CSRF token, injected into `signup.html`'s existing `#signup-form` element (e.g. via a `{{csrf_token}}` placeholder substituted the same way `dashboard.html`'s `{{username}}` placeholder already is), so the browser's native `<form method="POST">` submission includes it as a normal form field named `csrf_token`.

### FR-04: Token Injected into Login's Rendered HTML
`login_page()`'s response HTML must expose the session's CSRF token to the page's existing inline `fetch()`-submission script — via a `data-csrf-token` attribute (or equivalent) on an element already present in `login.html` (e.g. `#login-form`) — substituted the same way, so client-side JavaScript can read it without a separate network round-trip.

### FR-05: Login's `fetch()` Includes the Token
`login.html`'s existing inline submit handler (the `fetch('/login', { method: 'POST', body: formData })` call) must be updated to append the token read from the `data-csrf-token` attribute into the `FormData` it sends, under the field name `csrf_token`, so `login_post()` can read it the same way it reads `username`/`password` (as a `Form(...)` field).

### FR-06: Signup POST Validates the Token
`signup_post()` must accept a `csrf_token: str = Form(...)` field (alongside the existing `username`, `email`, `password` fields) and, before calling `auth_service.signup(...)`, verify it against `request.session.get("csrf_token")` using `verify_csrf_token()`. On failure, return `403` without calling `auth_service.signup(...)`.

### FR-07: Login POST Validates the Token
`login_post()` must accept a `csrf_token: str = Form(...)` field (alongside the existing `username`, `password` fields) and, before calling `auth_service.login(...)`, verify it against `request.session.get("csrf_token")` using `verify_csrf_token()`. On failure, return `403` without calling `auth_service.login(...)`.

### FR-08: Failure Response Shape Matches Each Route's Existing Style
- `signup_post()`'s CSRF failure response must be an `HTMLResponse` with `status_code=403` and a plain-text/HTML error message (matching the existing style of `auth_service.signup()`'s own failure responses, e.g. `HTMLResponse("Username already exists", status_code=400)`), e.g. `HTMLResponse("Invalid or missing CSRF token.", status_code=403)`.
- `login_post()`'s CSRF failure response must be a `JSONResponse` with `status_code=403` and a `{"success": False, "error": "..."}` body (matching the existing style of `auth_service.login()`'s own failure responses), e.g. `JSONResponse({"success": False, "error": "Invalid or missing CSRF token."}, status_code=403)`.

### FR-09: No Unrelated Vulnerability Fixes
This change must not modify `auth_service.py`'s query logic (VULN-1), `security.py`'s hashing (VULN-5), `/search`'s query/escaping (VULN-3), `/download/db`'s session check (VULN-6), `/welcome`'s escaping (VULN-2), or the `slowapi` rate-limiting decorators/wiring (VULN-7). `/logout` gains no token requirement (see §2).

---

## 5. Non-Functional Requirements

### NFR-01: No New Dependency
Token generation and verification use only Python's standard-library `secrets` module (`token_hex`, `compare_digest`), already imported elsewhere in the codebase (`main.py`). No package is added to `backend/pyproject.toml` or the root `pyproject.toml`.

### NFR-02: Constant-Time Comparison
Token comparison must use `secrets.compare_digest`, not `==`, to avoid a timing side-channel on token matching.

### NFR-03: Token Lives in the Existing Session
The CSRF token is stored under `request.session["csrf_token"]`, using the same `itsdangerous`-signed, cookie-backed session mechanism already established by `SessionMiddleware` (VULN-4 remediation) — no new session store, cookie, or middleware is introduced.

### NFR-04: One Token Per Session, Reused Across Page Loads
A session that already has a `csrf_token` value is not issued a new one on a subsequent `GET /login`/`GET /signup` — the existing value is reused and re-rendered into the page, so a user with multiple open tabs of the same form does not have earlier tabs' tokens invalidated by loading the form again.

### NFR-05: Response Shape Preserved for Non-CSRF Failures and Successes
For requests carrying a valid, matching token, `signup_post()`/`login_post()` response payloads, status codes, and redirect targets are unchanged from pre-fix behavior for all existing success/failure paths (successful signup/login, duplicate username, missing username/email/password, wrong password, nonexistent username) — the only new behavior is the `403` path for a missing/mismatched token, checked before those existing paths execute.

### NFR-06: Minimal Diff
The change is limited to: the new `csrf.py` module, `signup_page()`/`login_page()`/`signup_post()`/`login_post()` in `auth.py`, and the two template files' markup/inline script. No other route, function, or file is modified.

---

## 6. Success Paths

**SP-01 — Normal browser login flow**: a client requests `GET /login` → a token is generated (first visit) or reused (returning session) and embedded in the page → the page's `fetch()` script reads the token and includes it in its `POST /login` body along with `username`/`password` → the token matches the session's stored value → `login_post()` proceeds to `auth_service.login()` exactly as before, returning its existing success/failure JSON.

**SP-02 — Normal browser signup flow**: a client requests `GET /signup` → a token is generated/reused and embedded as a hidden form field → the browser's native form POST to `/signup` automatically includes `csrf_token` alongside `username`/`email`/`password` → the token matches → `signup_post()` proceeds to `auth_service.signup()` exactly as before.

**SP-03 — Multiple tabs, same session**: a user opens `/login` in two browser tabs. Both pages render the same token (per NFR-04, since the session already has one after the first). Submitting from either tab succeeds — neither invalidates the other.

**SP-04 — Returning after a successful login**: after a successful login clears/repopulates the session with `user_id`/`username`/`email` (per `auth_service.login()`'s existing behavior, unchanged by this fix), a subsequent visit to `/login` or `/signup` (e.g. after logout) generates a fresh token if the session no longer has one (logout via `request.session.clear()` removes `csrf_token` along with everything else, per `/logout`'s existing full-clear behavior — unchanged by this fix).

---

## 7. Edge Cases

**EC-01 — POST with no `csrf_token` field at all**: a request to `/login` or `/signup` omits the `csrf_token` field entirely (e.g. a raw `curl` POST with only `username`/`password`, or a cross-site form that doesn't know the field exists). `Form(...)` (required field) causes FastAPI's own validation to reject the request before it reaches the route body — the fix must ensure this still surfaces as a client error (FastAPI's default `422` for a missing required form field) rather than a `500`; the token-verification logic in FR-06/FR-07 handles the case where the field is present but empty or wrong.

**EC-02 — POST with an empty-string `csrf_token`**: the field is present but empty (`csrf_token=`). `verify_csrf_token()` treats this as a mismatch (FR-01: empty/falsy values never verify), returning `403`.

**EC-03 — POST with a token from a different session**: an attacker captures a valid-looking token value (e.g. from their own session) and submits it against a victim's session cookie (or vice versa) — since the submitted token is compared only against the value stored in the session tied to the request's own session cookie, a token that doesn't match that specific session's stored value is rejected with `403`, regardless of whether it was a validly-generated token for some other session.

**EC-04 — POST with a stale token after `/logout`**: a user logs out (`request.session.clear()` removes `csrf_token`), then a replayed/cached page (e.g. via browser back-button or a saved HTML copy) submits the old token. Because the session no longer has any `csrf_token` value, `verify_csrf_token(None, <stale token>)` returns `False`, and the request is rejected with `403`.

**EC-05 — Cross-site form submission without a valid token (the attack this fix defends against)**: a malicious page hosted elsewhere renders a `<form action="http://localhost:3001/signup" method="POST">` with `username`/`email`/`password` fields (no `csrf_token`, or a guessed/fixed one) and auto-submits it while the victim's browser has a session cookie for the app. Because the attacker's page cannot read the victim's session-tied token (same-origin policy prevents reading the rendered `/signup` page's hidden field cross-origin), the submitted token is absent or wrong, and the request is rejected with `403` before `auth_service.signup()` runs.

**EC-06 — Valid token, otherwise-invalid credentials**: a request with a correct, matching `csrf_token` but wrong `username`/`password` (login) or a duplicate `username` (signup) proceeds past CSRF validation and reaches `auth_service.login()`/`auth_service.signup()`, which reject it with their existing, unchanged `401`/`400` behavior — CSRF validation and credential/uniqueness validation are independent checks, and a CSRF pass does not imply an auth pass.

**EC-07 — `/logout` remains unaffected**: `GET /logout` is invoked with no token of any kind (as today) and still clears the session and redirects to `/login`, exactly as before this fix — no `403` is possible on `/logout` since it performs no token check.

---

## 8. Acceptance Criteria

**AC-01**: Given `backend/app/core/csrf.py`, when reviewed, then it exposes `generate_csrf_token()` (via `secrets.token_hex`) and `verify_csrf_token()` (via `secrets.compare_digest`), with no new third-party dependency.

**AC-02**: Given a fresh `GET /login` or `GET /signup` request with no prior session, when the response HTML is inspected, then it contains a CSRF token value, and `request.session["csrf_token"]` is set to that same value server-side.

**AC-03**: Given a `POST /login` or `POST /signup` request with a `csrf_token` matching the requester's own session value, when processed, then the request proceeds to `auth_service.login()`/`auth_service.signup()` exactly as it would have pre-fix, with identical success/failure response shapes for valid vs. invalid credentials.

**AC-04**: Given a `POST /login` or `POST /signup` request with a missing, empty, or mismatched `csrf_token` relative to the requester's session, when processed, then the response is `403` (JSON for `/login`, `HTMLResponse` for `/signup`) and `auth_service.login()`/`auth_service.signup()` is never invoked.

**AC-05**: Given a normal end-to-end browser flow (`GET` the page, then submit the rendered form/fetch from that same page/session), when executed for both login and signup, then the request succeeds (subject to credential correctness) exactly as before this fix — the CSRF mechanism is invisible to a legitimate same-origin user.

**AC-06**: Given `GET /logout`, when requested, then it behaves exactly as before this fix — no CSRF token is required, generated, or checked on this route.

**AC-07**: Given `backend/app/services/auth_service.py`, `backend/app/core/security.py`, and the `slowapi` rate-limiting wiring in `main.py`/`auth.py`, when compared to their pre-fix state, then they are unchanged by this document.

**AC-08**: Vulnerability #8 (CSRF on `/login` and `/signup`) is considered fixed.

**AC-09**: Vulnerabilities #2, #3, #6, #7 remain intentionally unchanged; all are already remediated by prior specs and untouched here.

---

## 9. Test Cases

| ID | Scenario | Precondition | Expected Result |
|---|---|---|---|
| TC-01 | Valid token, correct credentials — login succeeds as before | User registered; `GET /login` fetched first to obtain a session token | `POST /login` with matching `csrf_token` + correct `username`/`password` → `200`/JSON `{"success": true, "redirect": "/welcome"}`, identical to pre-fix behavior |
| TC-02 | Valid token, correct data — signup succeeds as before | `GET /signup` fetched first to obtain a session token | `POST /signup` with matching `csrf_token` + valid unique `username`/`email`/`password` → `302` redirect to `/login`, identical to pre-fix behavior |
| TC-03 | Missing token — login rejected | Session exists with a `csrf_token` value | `POST /login` with `username`/`password` but no `csrf_token` field → `422` (FastAPI required-field validation) or, if the field is sent empty, `403` per EC-02; in either case `auth_service.login()` is never reached |
| TC-04 | Missing token — signup rejected | Session exists with a `csrf_token` value | `POST /signup` with `username`/`email`/`password` but no `csrf_token` field → `422`/`403` per TC-03's logic; `auth_service.signup()` is never reached |
| TC-05 | Stale/mismatched token (reused from a different session) — login rejected | Two separate sessions/cookie jars each with their own `csrf_token` | `POST /login` using session A's cookie but session B's `csrf_token` value → `403` JSON error; `auth_service.login()` not invoked |
| TC-06 | Stale/mismatched token (reused from a different session) — signup rejected | Two separate sessions/cookie jars each with their own `csrf_token` | `POST /signup` using session A's cookie but session B's `csrf_token` value → `403` HTML error; `auth_service.signup()` not invoked |
| TC-07 | Normal end-to-end browser flow — login | None | `GET /login` in a browser, submit the rendered form with correct credentials via its existing `fetch()` flow → succeeds and redirects to `/welcome`, with no visible change in user experience |
| TC-08 | Normal end-to-end browser flow — signup | None | `GET /signup` in a browser, fill and submit the rendered form → succeeds and redirects to `/login`, with no visible change in user experience |
| TC-09 | Token reused across multiple page loads in the same session | Session already has a `csrf_token` | A second `GET /login` (or `/signup`) in the same session renders the same token value as the first; both remain valid for submission |
| TC-10 | `/logout` unaffected | Authenticated session | `GET /logout` → session cleared, redirect to `/login`, exactly as before this fix; no `403`, no token required |
| TC-11 | Valid token but wrong credentials still fails on auth grounds, not CSRF | Session with a valid `csrf_token`; existing user account | `POST /login` with correct `csrf_token` but wrong `password` → `401` (not `403`) with the standard invalid-credentials JSON error |

---

## 10. Verification Steps

1. Start the application from the project root:
   ```
   uv run backend/app/main.py
   ```
   Confirm it is listening at `http://localhost:3001`.

2. **Token present on page load (AC-02):**
   ```
   curl -s -c cookies.txt http://localhost:3001/login | grep -o 'data-csrf-token="[^"]*"'
   curl -s -c cookies2.txt http://localhost:3001/signup | grep -o 'name="csrf_token" value="[^"]*"'
   ```
   Expected: each command prints a non-empty token value; the cookie jars (`cookies.txt`, `cookies2.txt`) contain the session cookie.

3. **Valid token — login succeeds (TC-01, AC-03):**
   - Register a test user first via `/signup` (see step 4 for the CSRF-aware signup flow), then:
     ```
     TOKEN=$(curl -s -c cookies.txt http://localhost:3001/login | grep -o 'data-csrf-token="[^"]*"' | cut -d'"' -f2)
     curl -i -b cookies.txt -X POST http://localhost:3001/login \
       -d "username=<registered-username>" -d "password=<correct-password>" -d "csrf_token=$TOKEN"
     ```
   Expected: `200` and JSON `{"success": true, "redirect": "/welcome"}`.

4. **Valid token — signup succeeds (TC-02, AC-03):**
   ```
   TOKEN=$(curl -s -c cookies2.txt http://localhost:3001/signup | grep -o 'name="csrf_token" value="[^"]*"' | cut -d'"' -f2)
   curl -i -b cookies2.txt -X POST http://localhost:3001/signup \
     -d "username=csrftestuser" -d "email=csrftestuser@example.com" \
     -d "password=Password123" -d "csrf_token=$TOKEN"
   ```
   Expected: `302` redirect to `/login`.

5. **Missing token rejected (TC-03, TC-04, AC-04):**
   ```
   curl -i -b cookies.txt -X POST http://localhost:3001/login \
     -d "username=someuser" -d "password=wrong"
   ```
   Expected: `422` (missing required field) or `403` if the field is sent empty — not a `200`/`401` reflecting normal credential processing.

6. **Mismatched token rejected (TC-05, TC-06, AC-04):**
   ```
   curl -i -c cookies3.txt http://localhost:3001/login > /dev/null
   OTHER_TOKEN="deliberately-wrong-token-value"
   curl -i -b cookies.txt -X POST http://localhost:3001/login \
     -d "username=someuser" -d "password=wrong" -d "csrf_token=$OTHER_TOKEN"
   ```
   Expected: `403` JSON error; response body indicates an invalid/missing CSRF token, not standard invalid-credentials text.

7. **End-to-end browser flow (TC-07, TC-08, AC-05):**
   - Open `http://localhost:3001/signup` in a real browser, fill in the form, submit — confirm it redirects to `/login` with no visible behavior change.
   - Open `http://localhost:3001/login`, submit valid credentials for the account just created — confirm it redirects to `/welcome` with no visible behavior change.

8. **`/logout` unaffected (TC-10, AC-06):**
   ```
   curl -i -b cookies.txt http://localhost:3001/logout
   ```
   Expected: `302` redirect to `/login`, identical to pre-fix behavior; no token involved.

9. **Valid token, wrong credentials — still 401, not 403 (TC-11):**
   ```
   TOKEN=$(curl -s -c cookies4.txt http://localhost:3001/login | grep -o 'data-csrf-token="[^"]*"' | cut -d'"' -f2)
   curl -i -b cookies4.txt -X POST http://localhost:3001/login \
     -d "username=csrftestuser" -d "password=WrongPassword" -d "csrf_token=$TOKEN"
   ```
   Expected: `401` JSON `{"success": false, "error": "Invalid username or password."}` — CSRF check passed, credential check failed independently.

10. **Other vulnerabilities/fixes unaffected (AC-07, AC-09):**
    ```
    git diff -- backend/app/services/auth_service.py backend/app/core/security.py
    ```
    Expected: no output.
    ```
    for i in 1 2 3 4 5 6; do
      TOKEN=$(curl -s -c cookies5.txt http://localhost:3001/login | grep -o 'data-csrf-token="[^"]*"' | cut -d'"' -f2)
      curl -s -o /dev/null -w "%{http_code}\n" -b cookies5.txt -X POST http://localhost:3001/login \
        -d "username=nonexistent" -d "password=wrong" -d "csrf_token=$TOKEN"
    done
    ```
    Expected: the rate-limiting behavior from VULN-7 (5 allowed, 6th returns `429`) still applies on top of CSRF validation.
