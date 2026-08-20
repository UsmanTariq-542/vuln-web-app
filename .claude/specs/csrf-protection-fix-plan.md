# Implementation Plan

## CSRF Protection Fix (VULN-8)

**Version:** 1.0.0
**Source Spec:** `.claude/specs/csrf-protection-fix.md`
**Companion Documents:** `docs/PRD.md`, `docs/TDD.md`, `.claude/specs/app-foundation.md`, `.claude/specs/session-hijacking-fix.md`

---

## 0. Plan Scope

This plan implements only what `.claude/specs/csrf-protection-fix.md` specifies: a session-stored CSRF token generated on `GET /login`/`GET /signup`, injected into their rendered HTML, and validated on `POST /login`/`POST /signup`. It does **not** touch:

- SQL query construction anywhere (`auth_service.py`'s VULN-1 fix, `auth.py`'s `/search` VULN-3 fix).
- Password hashing (`security.py`'s bcrypt VULN-5 fix).
- Session cookie configuration — `SECRET_KEY` sourcing, `https_only`, `max_age` (VULN-4 fix) — the CSRF token is stored as an additional key in the same existing session dict, no `SessionMiddleware` parameter changes.
- The `slowapi` `Limiter`/`RateLimitExceeded` wiring or the `@limiter.limit("5/minute")` decorators (VULN-7 fix) — both remain exactly as they are, alongside the new CSRF checks.
- `/download/db`'s session check (VULN-6 fix), `/welcome`'s escaping (VULN-2 fix).
- `/logout` — no token requirement is added; its route is untouched.
- `auth_service.py` itself — CSRF validation happens in the route layer (`auth.py`), before `auth_service.signup()`/`auth_service.login()` are called; their signatures and bodies are unchanged.

Files touched by the implementation phase: `backend/app/core/csrf.py` (new), `backend/app/api/routes/auth.py`, `frontend/templates/login.html`, `frontend/templates/signup.html`. This plan document itself makes no code changes.

---

## Phase 1 — Baseline Verification (pre-change)

**Goal:** Confirm the current unprotected state matches the spec's description before making any change.

**Steps:**
1. Start the app: `uv run backend/app/main.py`, confirm listening on `http://localhost:3001`.
2. Confirm `GET /login`/`GET /signup` render no CSRF-related markup:
   ```
   curl -s http://localhost:3001/login | grep -i csrf
   curl -s http://localhost:3001/signup | grep -i csrf
   ```
   Expected (pre-fix): no output from either command.
3. Confirm a bare `POST /login`/`POST /signup` (no `csrf_token` field) currently succeeds/fails only on credential grounds:
   ```
   curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:3001/login \
     -d "username=nonexistent" -d "password=wrong"
   ```
   Expected (pre-fix): `401` (not `403`/`422` — no CSRF field is required today).
4. Confirm current signatures in `backend/app/api/routes/auth.py`:
   ```python
   @router.get("/signup")
   def signup_page():
       return HTMLResponse(_read_template("signup.html"))

   @router.post("/signup")
   @limiter.limit("5/minute")
   def signup_post(
       request: Request,
       username: str = Form(...),
       email: str = Form(...),
       password: str = Form(...),
   ):
       return auth_service.signup(username, email, password)

   @router.get("/login")
   def login_page():
       return HTMLResponse(_read_template("login.html"))

   @router.post("/login")
   @limiter.limit("5/minute")
   def login_post(
       request: Request,
       username: str = Form(...),
       password: str = Form(...),
   ):
       return auth_service.login(request, username, password)
   ```
   Note: `login_post()` already has `request: Request` (added for the VULN-7 rate-limit decorator and used by `auth_service.login()`); `signup_page()` and `login_page()` currently have no parameters at all; `signup_post()` has `request: Request` (added for VULN-7) but does not currently use it in its body.
5. Confirm `frontend/templates/login.html`'s inline submit handler currently builds `FormData` with only the form's native fields (`username`, `password`) and no token, and `signup.html`'s `#signup-form` has no hidden `csrf_token` input.

No code is modified in this phase — it only establishes the baseline referenced by AC-02/AC-04 in the spec.

---

## Phase 2 — Create `backend/app/core/csrf.py`

**Goal:** Apply FR-01, NFR-01, NFR-02 from the spec.

**New file:** `backend/app/core/csrf.py`

```python
import secrets


def generate_csrf_token() -> str:
    return secrets.token_hex(32)


def verify_csrf_token(session_token: str | None, submitted_token: str | None) -> bool:
    if not session_token or not submitted_token:
        return False
    return secrets.compare_digest(session_token, submitted_token)
```

Notes:
- `generate_csrf_token()` mirrors the existing `secrets.token_hex(32)` pattern already used in `main.py` for the ephemeral `SECRET_KEY` fallback — same strength, same standard-library call, no new dependency (NFR-01).
- `verify_csrf_token()` treats `None` or empty-string input on either side as an automatic mismatch (`False`) before ever calling `secrets.compare_digest`, so it never raises on missing values (FR-01) and satisfies EC-01/EC-02/EC-04 (missing field, empty field, cleared-session token all resolve to `False`).
- `secrets.compare_digest` is used for the actual comparison to avoid a timing side-channel (NFR-02).
- This module sits alongside `backend/app/core/security.py` (the existing bcrypt module), matching the codebase's existing `core/` convention for security-related helpers — `security.py` itself is not modified.

---

## Phase 3 — Token Generation and Injection in `signup_page()`/`login_page()`

**Goal:** Apply FR-02, FR-03, FR-04, NFR-03, NFR-04 from the spec.

**File:** `backend/app/api/routes/auth.py`

**New import** (added to the existing import block):

Before:
```python
import html
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.db.session import DB_PATH, get_db
from app.services import auth_service
```

After:
```python
import html
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.csrf import generate_csrf_token, verify_csrf_token
from app.db.session import DB_PATH, get_db
from app.services import auth_service
```

Note: `JSONResponse` is added to the `fastapi.responses` import because `login_post()`'s CSRF-failure path (Phase 4) returns one directly from `auth.py` (previously, all `JSONResponse` usage lived inside `auth_service.py`).

**Exact change to `signup_page()`:**

Before:
```python
@router.get("/signup")
def signup_page():
    return HTMLResponse(_read_template("signup.html"))
```

After:
```python
@router.get("/signup")
def signup_page(request: Request):
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = generate_csrf_token()
    csrf_token = request.session["csrf_token"]

    page_html = _read_template("signup.html")
    page_html = page_html.replace("{{csrf_token}}", html.escape(csrf_token))
    return HTMLResponse(page_html)
```

**Exact change to `login_page()`:**

Before:
```python
@router.get("/login")
def login_page():
    return HTMLResponse(_read_template("login.html"))
```

After:
```python
@router.get("/login")
def login_page(request: Request):
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = generate_csrf_token()
    csrf_token = request.session["csrf_token"]

    page_html = _read_template("login.html")
    page_html = page_html.replace("{{csrf_token}}", html.escape(csrf_token))
    return HTMLResponse(page_html)
```

Notes:
- Both routes gain a `request: Request` parameter (FR-02) — neither had one before.
- The `if "csrf_token" not in request.session:` check (NFR-04) ensures a session that already has a token keeps it across repeated page loads — matching the exact conditional style (`if "X" not in request.session:`) already used elsewhere in this file (`download_db()`, `welcome_page()`) for consistency with the codebase's established pattern, adapted here to a positive-generate-if-absent form rather than a redirect.
- `html.escape(csrf_token)` is applied before substitution, consistent with the file's existing escaping discipline (VULN-2's `welcome_page()`), even though a `secrets.token_hex` value can never itself contain HTML-special characters — this is defensive consistency, not a required behavior change, and does not alter the token's actual value being compared later.
- The `page_html.replace("{{csrf_token}}", ...)` mechanism mirrors the exact `str.replace()` substitution pattern already used for `{{username}}` in `welcome_page()` (per `app-foundation.md` §2's "runtime string substitution" business rule) — no template engine is introduced (NFR-06).

---

## Phase 4 — Token Validation in `signup_post()`/`login_post()`

**Goal:** Apply FR-06, FR-07, FR-08, NFR-05 from the spec, with the exact 403 response shape matching each route's existing style.

**File:** `backend/app/api/routes/auth.py`

**Exact change to `signup_post()`:**

Before:
```python
@router.post("/signup")
@limiter.limit("5/minute")
def signup_post(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    return auth_service.signup(username, email, password)
```

After:
```python
@router.post("/signup")
@limiter.limit("5/minute")
def signup_post(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
):
    if not verify_csrf_token(request.session.get("csrf_token"), csrf_token):
        return HTMLResponse("Invalid or missing CSRF token.", status_code=403)
    return auth_service.signup(username, email, password)
```

**Exact change to `login_post()`:**

Before:
```python
@router.post("/login")
@limiter.limit("5/minute")
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    return auth_service.login(request, username, password)
```

After:
```python
@router.post("/login")
@limiter.limit("5/minute")
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
):
    if not verify_csrf_token(request.session.get("csrf_token"), csrf_token):
        return JSONResponse(
            {"success": False, "error": "Invalid or missing CSRF token."},
            status_code=403,
        )
    return auth_service.login(request, username, password)
```

Notes:
- Both routes gain `csrf_token: str = Form(...)` as a new required form field (FR-06/FR-07), placed after the existing fields to minimize positional-argument disruption (all parameters are keyword-bindable `Form(...)`/`Request` FastAPI dependencies, so ordering has no functional effect, but appending keeps the diff minimal and existing fields visually undisturbed).
- The CSRF check runs as the **first statement** in each function body, before any call into `auth_service` — a failure never reaches `auth_service.signup()`/`auth_service.login()` (FR-06/FR-07: "does not proceed with authentication").
- `signup_post()`'s failure response is `HTMLResponse("Invalid or missing CSRF token.", status_code=403)` — matching the plain-text `HTMLResponse(..., status_code=400)` style already used by `auth_service.signup()`'s own duplicate-username failure (FR-08).
- `login_post()`'s failure response is `JSONResponse({"success": False, "error": "..."}, status_code=403)` — matching the exact JSON shape already used by `auth_service.login()`'s own `401` failures (FR-08), so the existing `login.html` `fetch()` handler's `data.success`/`data.error` handling (unchanged, see Phase 5) renders it inline exactly like any other login error.
- `request.session.get("csrf_token")` (not `request.session["csrf_token"]`) is used so a session with no token at all (e.g. a raw request with a forged/absent session cookie) resolves to `None` rather than raising `KeyError` — `verify_csrf_token()`'s `None`-safe handling (Phase 2) converts this into a clean `False`/`403` (EC-01 partial coverage; full coverage of a wholly-missing field is FastAPI's own `422` per EC-01/NFR-05).
- For requests that pass the CSRF check, `auth_service.signup(username, email, password)`/`auth_service.login(request, username, password)` are called with **identical arguments** to the pre-fix code — no change to their existing success/failure response shapes (NFR-05).

---

## Phase 5 — Template Changes: `signup.html`

**Goal:** Apply FR-03 from the spec — a hidden form field the browser includes automatically on native form submission.

**File:** `frontend/templates/signup.html`

**Exact change** (inside the existing `#signup-form` element, placed as the first child so it reads naturally alongside the other fields without disturbing visual layout — hidden inputs render nothing regardless of position):

Before:
```html
            <form id="signup-form" class="auth-form" action="/signup" method="POST" novalidate>
                <h2 class="form-title">Sign Up</h2>
                <p class="form-subtitle">Create your account to access the lab</p>

                <div class="form-group">
                    <label for="username">Username</label>
```

After:
```html
            <form id="signup-form" class="auth-form" action="/signup" method="POST" novalidate>
                <input type="hidden" name="csrf_token" value="{{csrf_token}}">

                <h2 class="form-title">Sign Up</h2>
                <p class="form-subtitle">Create your account to access the lab</p>

                <div class="form-group">
                    <label for="username">Username</label>
```

Notes:
- No JavaScript change is needed for `signup.html` — the form is a standard `<form method="POST">` (not `fetch()`-based), so the browser automatically includes every named `<input>` inside it, including this hidden one, in the native POST body alongside `username`/`email`/`password`/`confirm_password` (`confirm_password` itself is already client-side-only and not sent to the server, per the existing password-match JS — unchanged).
- The `{{csrf_token}}` placeholder is substituted server-side by `signup_page()` (Phase 3) using the same `str.replace()` mechanism as `{{username}}` in `dashboard.html`.
- No other part of `signup.html` (header, theme toggle, password-mismatch script, footer) is touched.

---

## Phase 6 — Template Changes: `login.html`

**Goal:** Apply FR-04, FR-05 from the spec — expose the token to the page's inline `fetch()` script and include it in the POST body.

**File:** `frontend/templates/login.html`

**Exact change 1 — carry the token via a `data-csrf-token` attribute on `#login-form`:**

Before:
```html
            <form id="login-form" class="auth-form" novalidate>
```

After:
```html
            <form id="login-form" class="auth-form" data-csrf-token="{{csrf_token}}" novalidate>
```

**Exact change 2 — include the token in the `fetch()` body:**

Before:
```javascript
    <script>
        document.getElementById('login-form').addEventListener('submit', async function (e) {
            e.preventDefault();

            const errorEl = document.getElementById('login-error');
            errorEl.style.display = 'none';

            const formData = new FormData(this);

            try {
                const response = await fetch('/login', {
                    method: 'POST',
                    body: formData
                });
```

After:
```javascript
    <script>
        document.getElementById('login-form').addEventListener('submit', async function (e) {
            e.preventDefault();

            const errorEl = document.getElementById('login-error');
            errorEl.style.display = 'none';

            const formData = new FormData(this);
            formData.append('csrf_token', this.dataset.csrfToken);

            try {
                const response = await fetch('/login', {
                    method: 'POST',
                    body: formData
                });
```

Notes:
- `data-csrf-token="{{csrf_token}}"` is placed on `#login-form` itself (FR-04's suggested container element), substituted server-side by `login_page()` (Phase 3) using the same mechanism as `signup.html`'s hidden input.
- `this.dataset.csrfToken` reads the `data-csrf-token` attribute (the browser's standard camelCase `dataset` mapping for a hyphenated `data-*` attribute) from the form element the submit handler is already bound to (`this` inside the listener is `#login-form`) — no new `document.getElementById(...)` lookup is needed.
- `formData.append('csrf_token', ...)` adds the token as an additional field in the same `FormData` object already being sent as the `fetch()` body — `login_post()` (Phase 4) reads it the same way it reads `username`/`password`, via `Form(...)`.
- No other part of `login.html` (header, theme toggle, error-display logic, redirect-on-success logic) is touched.

---

## Phase 7 — Static Review Against Spec Requirements

**Goal:** Before running the app, verify the diff satisfies every FR/NFR without side effects.

**Checklist:**
- [ ] FR-01: `csrf.py` exposes `generate_csrf_token()`/`verify_csrf_token()` using only `secrets`; no new dependency.
- [ ] FR-02: `signup_page()`/`login_page()` both gain `request: Request` and generate-if-absent a `request.session["csrf_token"]`.
- [ ] FR-03: `signup.html` has a hidden `csrf_token` input inside `#signup-form`.
- [ ] FR-04: `login.html`'s `#login-form` carries `data-csrf-token="{{csrf_token}}"`.
- [ ] FR-05: `login.html`'s inline `fetch()` script appends `csrf_token` to the `FormData` it sends.
- [ ] FR-06: `signup_post()` requires `csrf_token: str = Form(...)` and validates it before calling `auth_service.signup(...)`.
- [ ] FR-07: `login_post()` requires `csrf_token: str = Form(...)` and validates it before calling `auth_service.login(...)`.
- [ ] FR-08: `signup_post()`'s failure is `HTMLResponse(..., status_code=403)`; `login_post()`'s failure is `JSONResponse({"success": False, "error": ...}, status_code=403)`.
- [ ] FR-09 / NFR-06: no changes to `auth_service.py`, `security.py`, `/search`, `/download/db`, `/welcome`, the `slowapi` wiring, or `/logout`.
- [ ] NFR-01: no new third-party dependency.
- [ ] NFR-02: comparison uses `secrets.compare_digest`.
- [ ] NFR-03: token stored in `request.session`, no new middleware/cookie/store.
- [ ] NFR-04: existing session token is reused (not regenerated) on repeat `GET` requests.
- [ ] NFR-05: for a request with a valid token, response shapes for all existing success/failure paths are byte-for-byte unchanged from pre-fix.
- [ ] `git diff` (once implemented) touches only: `backend/app/core/csrf.py` (new), `backend/app/api/routes/auth.py`, `frontend/templates/login.html`, `frontend/templates/signup.html`.

---

## Phase 8 — Functional Verification (post-change)

**Goal:** Execute the verification steps from `.claude/specs/csrf-protection-fix.md` §10 against the modified code.

1. Restart the app:
   ```
   uv run backend/app/main.py
   ```
   Confirm it is listening at `http://localhost:3001`.

2. **Token present on page load (AC-02):**
   ```
   curl -s -c cookies.txt http://localhost:3001/login | grep -o 'data-csrf-token="[^"]*"'
   curl -s -c cookies2.txt http://localhost:3001/signup | grep -o 'name="csrf_token" value="[^"]*"'
   ```
   Expected: each prints a non-empty token.

3. **Valid token — signup succeeds (TC-02, AC-03):**
   ```
   TOKEN=$(curl -s -c cookies2.txt http://localhost:3001/signup | grep -o 'name="csrf_token" value="[^"]*"' | cut -d'"' -f2)
   curl -i -b cookies2.txt -X POST http://localhost:3001/signup \
     -d "username=csrftestuser" -d "email=csrftestuser@example.com" \
     -d "password=Password123" -d "csrf_token=$TOKEN"
   ```
   Expected: `302` redirect to `/login`.

4. **Valid token — login succeeds (TC-01, AC-03):**
   ```
   TOKEN=$(curl -s -c cookies.txt http://localhost:3001/login | grep -o 'data-csrf-token="[^"]*"' | cut -d'"' -f2)
   curl -i -b cookies.txt -X POST http://localhost:3001/login \
     -d "username=csrftestuser" -d "password=Password123" -d "csrf_token=$TOKEN"
   ```
   Expected: `200` and JSON `{"success": true, "redirect": "/welcome"}`.

5. **Missing token rejected (TC-03, TC-04, AC-04):**
   ```
   curl -i -b cookies.txt -X POST http://localhost:3001/login \
     -d "username=someuser" -d "password=wrong"
   ```
   Expected: `422` (FastAPI required-field validation).

6. **Mismatched token rejected (TC-05, TC-06, AC-04):**
   ```
   curl -i -c cookies3.txt http://localhost:3001/login > /dev/null
   curl -i -b cookies.txt -X POST http://localhost:3001/login \
     -d "username=someuser" -d "password=wrong" -d "csrf_token=deliberately-wrong-token-value"
   ```
   Expected: `403` JSON `{"success": false, "error": "Invalid or missing CSRF token."}`.

7. **End-to-end browser flow (TC-07, TC-08, AC-05):**
   - In a real browser: `GET /signup`, fill and submit → redirects to `/login` with no visible change.
   - `GET /login`, submit valid credentials → redirects to `/welcome` with no visible change.

8. **`/logout` unaffected (TC-10, AC-06):**
   ```
   curl -i -b cookies.txt http://localhost:3001/logout
   ```
   Expected: `302` to `/login`, unchanged.

9. **Valid token, wrong credentials — 401 not 403 (TC-11):**
   ```
   TOKEN=$(curl -s -c cookies4.txt http://localhost:3001/login | grep -o 'data-csrf-token="[^"]*"' | cut -d'"' -f2)
   curl -i -b cookies4.txt -X POST http://localhost:3001/login \
     -d "username=csrftestuser" -d "password=WrongPassword" -d "csrf_token=$TOKEN"
   ```
   Expected: `401` JSON `{"success": false, "error": "Invalid username or password."}`.

10. **Other fixes unaffected (AC-07, AC-09):**
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
    Expected: 5 lines of `401`, then `429` (VULN-7's rate limit still applies on top of CSRF validation).

---

## Rollback Plan

If Phase 8 verification fails (e.g., legitimate browser flows break, or an unrelated route is affected), revert the four touched files via:
```
git checkout -- backend/app/api/routes/auth.py frontend/templates/login.html frontend/templates/signup.html
rm backend/app/core/csrf.py
```
No other file requires rollback since none other is touched.
