# Implementation Plan

## Rate Limiting Fix (VULN-7)

**Version:** 1.0.0
**Source Spec:** `.claude/specs/rate-limiting-fix.md`
**Companion Documents:** `docs/PRD.md`, `docs/TDD.md`, `.claude/specs/app-foundation.md`

---

## 0. Plan Scope

This plan implements only what `.claude/specs/rate-limiting-fix.md` specifies: adding `slowapi` as a dependency, wiring a `Limiter` into `backend/app/main.py`, and rate-limiting `login_post()`/`signup_post()` in `backend/app/api/routes/auth.py`. It does **not** touch:

- SQL query construction anywhere (`auth_service.py`'s VULN-1 fix, `auth.py`'s `/search` VULN-3 fix) — untouched.
- Password hashing (`security.py`'s bcrypt VULN-5 fix) — untouched.
- Session/cookie configuration beyond what's strictly needed to add the limiter — `SECRET_KEY` sourcing, `https_only`, `max_age` (VULN-4 fix) are untouched; `SessionMiddleware` registration itself is not modified, only where the new limiter setup is placed relative to it.
- `/download/db`'s session check (VULN-6 fix) — untouched.
- `/welcome`'s escaping (VULN-2 fix) — untouched.
- Any route other than `POST /login` and `POST /signup` — `GET /`, `GET /signup`, `GET /login`, `GET /welcome`, `GET /search`, `GET /download/db`, `GET /logout` all remain unthrottled.
- CSRF protection (VULN-8) — remains unfixed, not added.

Files touched by the implementation phase: `backend/pyproject.toml`, `pyproject.toml` (root), `backend/app/main.py`, `backend/app/api/routes/auth.py`. This plan document itself makes no code changes.

---

## Phase 1 — Baseline Verification (pre-change)

**Goal:** Confirm the current unthrottled state matches the spec's description before making any change.

**Steps:**
1. Start the app: `uv run backend/app/main.py`, confirm listening on `http://localhost:3001`.
2. Run 6+ rapid `POST /login` requests and confirm none are throttled (all return `401`/`200` per existing `auth_service.login()` logic, never `429`):
   ```
   for i in 1 2 3 4 5 6; do
     curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:3001/login \
       -d "username=nonexistent" -d "password=wrong"
   done
   ```
   Expected (pre-fix): six `401` lines.
3. Confirm `backend/app/main.py`'s current VULN-7 comment and absence of any limiter:
   ```python
   # VULN-7: No Rate Limiting (intentional, by omission). No throttling
   # middleware is registered anywhere in this file -- do not add one.
   ```
4. Confirm `backend/pyproject.toml` and the root `pyproject.toml` do not list `slowapi` in `dependencies`.
5. Confirm `login_post()` already has a `request: Request` parameter, and `signup_post()` does not:
   ```python
   @router.post("/signup")
   def signup_post(
       username: str = Form(...),
       email: str = Form(...),
       password: str = Form(...),
   ):
       return auth_service.signup(username, email, password)


   @router.post("/login")
   def login_post(
       request: Request,
       username: str = Form(...),
       password: str = Form(...),
   ):
       return auth_service.login(request, username, password)
   ```

No code is modified in this phase — it only establishes the baseline referenced by AC-04/AC-07 in the spec.

---

## Phase 2 — Add the `slowapi` Dependency

**Goal:** Apply FR-01 from the spec.

**File 1: `backend/pyproject.toml`**

Before:
```toml
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn>=0.27.0",
    "python-multipart>=0.0.6",
    "itsdangerous>=2.0.0",
    "bcrypt>=4.0.0",
]
```

After:
```toml
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn>=0.27.0",
    "python-multipart>=0.0.6",
    "itsdangerous>=2.0.0",
    "bcrypt>=4.0.0",
    "slowapi>=0.1.9",
]
```

**File 2: `pyproject.toml` (project root)**

Before:
```toml
dependencies = [
    "bcrypt>=4.0.0",
    "fastapi>=0.141.1",
    "itsdangerous>=2.2.0",
    "python-multipart>=0.0.32",
    "uvicorn>=0.52.1",
]
```

After (inserted alphabetically, matching this file's existing alphabetical ordering convention):
```toml
dependencies = [
    "bcrypt>=4.0.0",
    "fastapi>=0.141.1",
    "itsdangerous>=2.2.0",
    "python-multipart>=0.0.32",
    "slowapi>=0.1.9",
    "uvicorn>=0.52.1",
]
```

Notes:
- `slowapi>=0.1.9` is the version-pinned string format used consistently by both files (`backend/pyproject.toml` uses unsorted insertion order matching its existing list; the root `pyproject.toml` is alphabetically sorted, so `slowapi` is inserted between `python-multipart` and `uvicorn` to preserve that ordering).
- No other line in either file changes.
- After this phase, run `cd backend && uv sync` (and, if the root project is separately synced, `uv sync` at the root) to install `slowapi` before Phase 5's functional verification — installation itself happens during implementation, not as a separate manual step outside this plan.

---

## Phase 3 — Wire the Limiter into `main.py`

**Goal:** Apply FR-02, FR-03 from the spec, placed correctly relative to existing middleware/router registration order (NFR-04: minimal diff, no reordering of unrelated setup).

**File:** `backend/app/main.py`

**Exact placement:** the `Limiter` is constructed and attached to `app.state.limiter`, and the exception handler is registered, in the same location currently occupied by the VULN-7 comment — **after** `SessionMiddleware` registration, **before** `app.include_router(auth_router)`. This preserves the file's existing top-to-bottom order: app creation → session middleware → (now) rate limiter setup → router inclusion → static mounts → `init_db()`. The limiter must be attached to `app.state` and the exception handler registered before `auth_router` is included, since the router's routes (once decorated in Phase 4) resolve `app.state.limiter` at request time — registering the router first would not itself break anything (FastAPI resolves `app.state` lazily per-request), but keeping setup-before-inclusion matches the existing pattern of "configure app state, then include routes" already used for `SessionMiddleware`.

**New imports** (added to the existing import block at the top of the file):

Before:
```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes.auth import router as auth_router
from app.db.session import init_db
```

After:
```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes.auth import router as auth_router
from app.db.session import init_db
```

**Exact setup change** (replacing the VULN-7 comment block):

Before:
```python
# VULN-7: No Rate Limiting (intentional, by omission). No throttling
# middleware is registered anywhere in this file -- do not add one.

app.include_router(auth_router)
```

After:
```python
# VULN-7 remediated: an in-memory, per-client-IP limiter is attached to
# app.state so route-level @limiter.limit(...) decorators (see auth.py's
# login_post()/signup_post()) can resolve it. See
# .claude/specs/rate-limiting-fix.md for scope and limitations (single
# process, in-memory counters -- not a distributed rate limiter).
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth_router)
```

Notes:
- `app.add_middleware(SessionMiddleware, ...)` (lines above this block) is entirely unchanged — no reordering, no parameter changes.
- The static-file mounts (`app.mount("/static/css", ...)`, `app.mount("/static/images", ...)`) and `init_db()` call below `app.include_router(auth_router)` are entirely unchanged and untouched.
- No new middleware class is registered via `app.add_middleware(...)` — `slowapi`'s recommended integration for this use case is `app.state.limiter` + an exception handler + per-route decorators, not a blanket middleware, matching the spec's route-scoped (not global) limiting requirement (FR-06).

---

## Phase 4 — Decorate `login_post()` and `signup_post()` in `auth.py`

**Goal:** Apply FR-04, FR-05 from the spec, using the exact limit value from NFR-01 (`"5/minute"`).

**File:** `backend/app/api/routes/auth.py`

**New import** (added to the existing import block at the top of the file):

Before:
```python
import html
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.db.session import DB_PATH, get_db
from app.services import auth_service
```

After:
```python
import html
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.db.session import DB_PATH, get_db
from app.services import auth_service

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
```

Note on the `limiter` reference used by the decorators: `slowapi`'s `@limiter.limit(...)` decorator needs a `Limiter` instance accessible at decoration time (module load), while the request-time enforcement reads the limiter from `request.app.state.limiter` (the same instance constructed in `main.py`, since `Limiter(key_func=get_remote_address)` in `auth.py` is only used to supply the decorator; `slowapi`'s `SlowAPIMiddleware`-free, exception-handler-based pattern resolves the actual limit state via `request.app.state.limiter` at call time). This mirrors `slowapi`'s standard documented usage: a module-level `Limiter` is created for the `@limiter.limit(...)` decorator syntax, and `app.state.limiter` (set in `main.py`, Phase 3) is what the decorator's underlying implementation consults through the `Request` object each of the decorated functions now receives.

**Exact decorator addition to `signup_post()`** (gains `request: Request`, since `slowapi` requires the decorated function to accept a `Request` parameter):

Before:
```python
@router.post("/signup")
def signup_post(
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
):
    return auth_service.signup(username, email, password)
```

Notes:
- `request: Request` is added as the first parameter (matching `login_post()`'s existing parameter ordering below) but is **not** passed to `auth_service.signup(...)` — that call's signature and behavior are unchanged (`auth_service.signup(username, email, password)`, exactly as before), per NFR-05 (no change to non-throttled response behavior).
- `@limiter.limit("5/minute")` is placed **below** `@router.post("/signup")` (decorators apply bottom-up; this ordering matches `slowapi`'s documented usage with FastAPI/Starlette route decorators).

**Exact decorator addition to `login_post()`** (already has `request: Request`, so only the decorator is added):

Before:
```python
@router.post("/login")
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
):
    return auth_service.login(request, username, password)
```

Notes:
- No parameter changes needed — `request: Request` was already present and is already passed to `auth_service.login(request, username, password)` exactly as before.
- The rate limit value and window are identical to `signup_post()`'s: **5 requests per minute per client IP** (NFR-01), applied independently per route (EC-03 in the spec — `/login` and `/signup` do not share a counter).

**No other function in `auth.py` is decorated or otherwise modified** — `index()`, `signup_page()`, `login_page()`, `download_db()`, `search_user()`, `welcome_page()`, `logout()` are all untouched (FR-06).

---

## Phase 5 — Static Review Against Spec Requirements

**Goal:** Before running the app, verify the diff satisfies every FR/NFR without side effects.

**Checklist:**
- [ ] FR-01: `slowapi` present in both `backend/pyproject.toml` and root `pyproject.toml` dependency lists, version-pinned in the existing format.
- [ ] FR-02: `Limiter(key_func=get_remote_address)` assigned to `app.state.limiter` in `main.py`.
- [ ] FR-03: `RateLimitExceeded` registered with `_rate_limit_exceeded_handler` via `app.add_exception_handler(...)` in `main.py`.
- [ ] FR-04: `login_post()` decorated with `@limiter.limit("5/minute")`.
- [ ] FR-05: `signup_post()` decorated with `@limiter.limit("5/minute")` and has gained a `request: Request` parameter, unused in the function body beyond satisfying the decorator's requirement.
- [ ] FR-06: no other route in `auth.py` carries a `@limiter.limit(...)` decorator or any other throttling.
- [ ] FR-07: a throttled request returns `429` with a JSON body (slowapi's default handler), never an unhandled exception.
- [ ] FR-08: `auth_service.py`, `security.py` are byte-for-byte unchanged; `/search`'s query/escaping, `/download/db`'s session check, `/welcome`'s escaping are all untouched; no CSRF middleware/tokens added.
- [ ] NFR-01: limit value is exactly `"5/minute"` on both decorated routes.
- [ ] NFR-02: no external store (Redis, etc.) configured — default in-memory `limits` storage only.
- [ ] NFR-03: limiter keys on `get_remote_address` (client IP), not a custom key function.
- [ ] NFR-04: diff is confined to the two `pyproject.toml` files, `main.py`'s import block + the VULN-7 comment/setup block (with `SessionMiddleware` registration and everything below `app.include_router(auth_router)` untouched), and `auth.py`'s import block + the two decorated function signatures.
- [ ] NFR-05: for requests within the limit, `login_post()`/`signup_post()` response status codes and bodies are unchanged from pre-fix behavior.

---

## Phase 6 — Functional Verification (post-change)

**Goal:** Execute the verification steps from `.claude/specs/rate-limiting-fix.md` §10 against the modified code.

1. Install the new dependency and restart the app:
   ```
   cd backend && uv sync
   uv run backend/app/main.py
   ```
   Confirm it is listening at `http://localhost:3001`.

2. **6th `/login` attempt is throttled (TC-01, AC-04):**
   ```
   for i in 1 2 3 4 5 6; do
     curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:3001/login \
       -d "username=nonexistent" -d "password=wrong"
   done
   ```
   Expected: five `401` lines, then a `429`.

3. **Window rollover restores access (TC-02, AC-06):**
   Wait 60+ seconds, then:
   ```
   curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:3001/login \
     -d "username=nonexistent" -d "password=wrong"
   ```
   Expected: `401` (processed normally, not `429`).

4. **`/welcome` and `/search` remain unthrottled (TC-03, TC-04, AC-05):**
   Immediately after exhausting the `/login` limit:
   ```
   curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3001/welcome
   for i in 1 2 3 4 5 6 7; do
     curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:3001/search?q=test"
   done
   ```
   Expected: `/welcome` returns `302`; all `/search` requests return `200`, none `429`.

5. **6th `/signup` attempt is throttled (TC-05, AC-03):**
   ```
   for i in 1 2 3 4 5 6; do
     curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:3001/signup \
       -d "username=user$i" -d "email=user$i@example.com" -d "password=Password123"
   done
   ```
   Expected: first 5 process normally, 6th returns `429`.

6. **`/login` and `/signup` limits are independent (TC-06):**
   After exhausting `/login`'s limit, confirm a fresh `/signup` request still succeeds (subject to its own allowance):
   ```
   curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:3001/signup \
     -d "username=independenttest" -d "email=independenttest@example.com" -d "password=Password123"
   ```
   Expected: `302` (not `429`).

7. **`/download/db` and `/logout` remain unthrottled (TC-09):**
   ```
   curl -i http://localhost:3001/download/db
   curl -i http://localhost:3001/logout
   ```
   Expected: both behave exactly as before this fix, never `429`.

8. **Source-level checks (AC-01, AC-02, AC-03):**
   - `backend/pyproject.toml` and root `pyproject.toml` list `slowapi`.
   - `backend/app/main.py` constructs `Limiter(key_func=get_remote_address)`, assigns it to `app.state.limiter`, and registers `RateLimitExceeded`/`_rate_limit_exceeded_handler`.
   - `backend/app/api/routes/auth.py`'s `login_post()` and `signup_post()` both carry `@limiter.limit("5/minute")`; `signup_post()` has a `request: Request` parameter.

9. **Other vulnerabilities/fixes unaffected (AC-09):**
   ```
   git diff -- backend/app/services/auth_service.py backend/app/core/security.py
   ```
   Expected: no output.
   ```
   curl -i http://localhost:3001/download/db
   ```
   Expected: unauthenticated request redirects to `/login`.

---

## Rollback Plan

If Phase 6 verification fails (e.g., legitimate logins get throttled unexpectedly, or `/welcome`/`/search` are accidentally affected), revert the four touched files via:
```
git checkout -- backend/pyproject.toml pyproject.toml backend/app/main.py backend/app/api/routes/auth.py
```
then run `cd backend && uv sync` to remove `slowapi` from the resolved environment if desired. No other file requires rollback since none other is touched.
