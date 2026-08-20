# Implementation Plan — Stored XSS Remediation (VULN-2)

**Version:** 1.0.0
**Source Spec:** `.claude/specs/stored-xss-fix.md`
**Companion Documents:** `docs/TDD.md`, `.claude/specs/sql-injection-fix.md`, `.claude/specs/session-hijacking-fix.md`, `.claude/specs/bcrypt-password-hashing.md`

---

## Phase 0 — Preconditions

- Confirm `backend/app/api/routes/auth.py`'s `welcome_page()` is in its current documented state (per `docs/TDD.md` §3.1.2, §4.1 row 2, §3.3.3 "Stored XSS Path"): it checks `"user_id" not in request.session` and redirects to `/login` if absent; otherwise it reads `dashboard.html` fresh from disk via `_read_template()` and substitutes `request.session["username"]` into the `{{username}}` placeholder with plain, unescaped `str.replace()`.
- Confirm `frontend/templates/dashboard.html` contains exactly one `{{username}}` placeholder occurrence, inside the `<span class="user-badge">Logged in as {{username}}</span>` element (line 40), and that this plan will not modify that file.
- Confirm no `html` module import currently exists at the top of `backend/app/api/routes/auth.py` (current imports are `pathlib.Path`, `fastapi.APIRouter`/`Form`/`Request`, `fastapi.responses.FileResponse`/`HTMLResponse`/`RedirectResponse`, and `app.db.session.DB_PATH`/`get_db`, `app.services.auth_service`).
- Confirm no new dependency is required — `html.escape()` is part of the Python standard library. `backend/pyproject.toml` and the root `pyproject.toml` need no change.

---

## Phase 1 — `auth.py`: Import the Standard-Library `html` Module

**File:** `backend/app/api/routes/auth.py`

**Current (top of file):**
```python
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.db.session import DB_PATH, get_db
from app.services import auth_service
```

**Target:**
```python
import html
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.db.session import DB_PATH, get_db
from app.services import auth_service
```

**Details:**
- Add `import html` as a new standard-library import, placed before `from pathlib import Path` to keep standard-library imports grouped ahead of third-party/local imports, consistent with the file's existing import ordering.
- No other import changes. `Form`, `Request`, `HTMLResponse`, etc. are all still used exactly as before.

**Corresponds to:** spec FR-01, NFR-01.

---

## Phase 2 — `welcome_page()`: Escape the Session Username Before Substitution

**File:** `backend/app/api/routes/auth.py`

**Current (vulnerable) construction:**
```python
@router.get("/welcome")
def welcome_page(request: Request):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=302)

    # VULN-2: Stored XSS (intentional). The username is substituted into the
    # template with no escaping -- a username stored with a <script>/<img
    # onerror> payload executes here on every load.
    html = _read_template("dashboard.html")
    html = html.replace("{{username}}", request.session["username"])
    return HTMLResponse(html)
```

**Target construction:**
```python
@router.get("/welcome")
def welcome_page(request: Request):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=302)

    # VULN-2 remediated: the username is HTML-escaped before substitution so
    # a stored <script>/<img onerror> payload renders as inert literal text
    # instead of executing. See .claude/specs/stored-xss-fix.md.
    page_html = _read_template("dashboard.html")
    safe_username = html.escape(request.session["username"])
    page_html = page_html.replace("{{username}}", safe_username)
    return HTMLResponse(page_html)
```

**Details:**
- The local variable previously named `html` (holding the template string) **must be renamed** (e.g. to `page_html`) — its current name shadows the newly imported `html` module within the function body, which would make `html.escape(...)` fail with `AttributeError: 'str' object has no attribute 'escape'`. This rename is a required consequence of Phase 1's import, not a stylistic choice.
- Insert a new line computing `safe_username = html.escape(request.session["username"])` immediately after the template is read and before the substitution.
- Change the `.replace("{{username}}", request.session["username"])` call to `.replace("{{username}}", safe_username)`.
- The `if "user_id" not in request.session` guard, the `RedirectResponse` on failure, the `_read_template("dashboard.html")` call itself, and the final `return HTMLResponse(...)` are all unchanged in behavior — only the value substituted for `{{username}}` changes, and the local variable holding the template text is renamed for correctness (Phase 1).
- Replace the existing "VULN-2: Stored XSS (intentional)" comment with a short comment noting the vulnerability is remediated and pointing at the spec, consistent with how prior remediations (VULN-1, VULN-4, VULN-5) updated their in-code comments.
- `html.escape()` is called with its default arguments (`quote=True`), which escapes `&`, `<`, `>`, `"`, and `'`.

**Corresponds to:** spec FR-01, FR-02, FR-03, NFR-02, NFR-03, NFR-04.

---

## Phase 3 — Confirm `dashboard.html` Is Untouched

This phase is a **verification-only** step; it modifies no code.

- Confirm `frontend/templates/dashboard.html` is not edited in any way: the `{{username}}` placeholder token, its position inside `<span class="user-badge">Logged in as {{username}}</span>`, and every other line of the file remain byte-for-byte identical to their pre-fix state.
- Confirm `_read_template()` (used by every route, not just `/welcome`) is not modified — templates continue to be read fresh from disk on every request with no caching layer introduced.
- Confirm no templating engine (Jinja2 or otherwise) is added to `backend/pyproject.toml` or the root `pyproject.toml`.

**Corresponds to:** spec FR-03, AC-05, Affected Files §3 ("Inspected but must NOT be modified").

---

## Phase 4 — Confirm Out-of-Scope Surfaces Are Untouched

This phase is a **verification-only** step; it modifies no code.

- Confirm `/search` (VULN-3) in `backend/app/api/routes/auth.py` is not modified: the reflected `q` parameter, the `f"<li>{row['username']} ({row['email']})</li>"` result-row construction, and the raw exception-message text in the `except` block all remain unescaped and string-concatenated exactly as before.
- Confirm `/download/db` (VULN-6) is not modified: still no authentication check.
- Confirm no rate-limiting middleware (VULN-7) or CSRF token/middleware (VULN-8) is added anywhere in `main.py` or `auth.py`.
- Confirm `backend/app/services/auth_service.py` (VULN-1, already remediated per `.claude/specs/sql-injection-fix.md`) is not modified.
- Confirm `backend/app/core/security.py` (VULN-5, already remediated per `.claude/specs/bcrypt-password-hashing.md`) is not modified.
- Confirm `backend/app/main.py` (VULN-4, already remediated per `.claude/specs/session-hijacking-fix.md`) is not modified — `SECRET_KEY` sourcing and `SessionMiddleware`'s `https_only=True`/`max_age=1800` are untouched.
- Confirm `backend/app/db/session.py` is unmodified — no schema change.
- Confirm no dependency is added to `backend/pyproject.toml` or the root `pyproject.toml`.

**Corresponds to:** spec FR-04, AC-07, Affected Files §3.

---

## Phase 5 — Manual Verification (per spec §10)

Run these after Phases 1–2 are implemented, using the exact commands and endpoints from the spec.

1. **Install dependencies and start the app:**
   ```
   cd backend && uv sync
   uv run backend/app/main.py
   ```
   Serves at `http://localhost:3001`.

2. **Register a script-payload username (TC-02):**
   ```
   curl -i -X POST http://localhost:3001/signup \
     --data-urlencode "username=<script>alert(1)</script>" \
     -d "email=xsstest@example.com" \
     -d "password=SomePassword123"
   ```
   Expect `302` to `/login`.

3. **Log in as that user and save the session cookie:**
   ```
   curl -i -c cookies.txt -X POST http://localhost:3001/login \
     --data-urlencode "username=<script>alert(1)</script>" \
     -d "password=SomePassword123"
   ```
   Expect `200` and `{"success": true, "redirect": "/welcome"}`.

4. **Request the dashboard and inspect the raw body (AC-02):**
   ```
   curl -s -b cookies.txt http://localhost:3001/welcome
   ```
   Expect the body to contain the literal text `&lt;script&gt;alert(1)&lt;/script&gt;` and **not** contain an unescaped `<script>alert(1)</script>` tag.

5. **Browser confirmation:** open `http://localhost:3001/welcome` in a browser with the same session (or log in via the UI with this username). Confirm no `alert()` dialog fires and the "Logged in as" text shows the payload as literal visible text.

6. **Repeat for individual HTML-significant characters (EC-03–EC-07):** register and log in usernames containing `&`, `<`/`>`, `"`, and `'` respectively; confirm each renders as its HTML entity (`&amp;`, `&lt;`/`&gt;`, `&quot;`, `&#x27;`) in the `/welcome` response body.

7. **Normal username unaffected (TC-01):**
   ```
   curl -i -X POST http://localhost:3001/signup \
     -d "username=alice123" -d "email=alice@example.com" -d "password=SomePassword123"
   curl -i -c cookies2.txt -X POST http://localhost:3001/login \
     -d "username=alice123" -d "password=SomePassword123"
   curl -s -b cookies2.txt http://localhost:3001/welcome
   ```
   Expect `Logged in as alice123` with no entity-encoding artifacts.

8. **`/search` remains unescaped (TC-10):**
   ```
   curl -s "http://localhost:3001/search?q=<script>alert(1)</script>"
   ```
   Expect the payload reflected unescaped in the response body.

9. **`/download/db` remains unauthenticated (TC-11):**
   ```
   curl -i http://localhost:3001/download/db
   ```
   Expect `200` and the raw SQLite file with no auth check.

10. **Source-level confirmation (AC-01):** inspect `backend/app/api/routes/auth.py`'s `welcome_page()` for the `html.escape()` call applied to `request.session["username"]` before the `.replace()` call.

11. **`dashboard.html` unmodified (AC-05):**
    ```
    git diff HEAD -- frontend/templates/dashboard.html
    ```
    Expect no output.

12. **Optional test suite:**
    ```
    cd backend && uv run --extra dev pytest
    ```

---

## Summary of File Changes

| File | Change | Phase |
|---|---|---|
| `backend/app/api/routes/auth.py` | Add `import html` | 1 |
| `backend/app/api/routes/auth.py` | `welcome_page()`: rename template-text local var, escape session username via `html.escape()` before `.replace()`, update in-code comment | 2 |
| `frontend/templates/dashboard.html` | None (verified unchanged) | 3 |
| `backend/app/api/routes/auth.py` (`/search`, `/download/db`) | None (verified unchanged) | 4 |
| `backend/app/services/auth_service.py` | None (verified unchanged) | 4 |
| `backend/app/core/security.py` | None (verified unchanged) | 4 |
| `backend/app/main.py` | None (verified unchanged) | 4 |
| `backend/app/db/session.py` | None (verified unchanged) | 4 |
| `backend/pyproject.toml` | None (no new dependency) | 0, 4 |
| `pyproject.toml` (root) | None (no new dependency) | 0, 4 |
