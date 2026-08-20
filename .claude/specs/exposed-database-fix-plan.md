# Implementation Plan

## Exposed Database Fix (VULN-6)

**Version:** 1.0.0
**Source Spec:** `.claude/specs/exposed-database-fix.md`
**Companion Documents:** `docs/PRD.md`, `docs/TDD.md`, `.claude/specs/app-foundation.md`

---

## 0. Plan Scope

This plan implements only what `.claude/specs/exposed-database-fix.md` specifies: adding a session-presence check to `download_db()` in `backend/app/api/routes/auth.py`, mirroring the existing check in `welcome_page()`. It does **not** touch:

- `/search` (VULN-3 — SQL injection, reflected XSS, exception leakage all remain string-concatenated and unescaped)
- `/welcome`'s own logic or `dashboard.html` (VULN-2 remediation already in place, left as-is)
- `backend/app/main.py` (`SECRET_KEY` sourcing, `SessionMiddleware` config — VULN-4 remediation, left as-is)
- `backend/app/core/security.py` (bcrypt — VULN-5 remediation, left as-is)
- `backend/app/services/auth_service.py` (parameterized queries — VULN-1 remediation, left as-is)
- Any rate-limiting or CSRF middleware (VULN-7, VULN-8 remain absent/unfixed)
- `backend/app/db/session.py`, database schema, or any template file

Single file touched by the implementation phase: `backend/app/api/routes/auth.py`. This plan document itself makes no code changes.

---

## Phase 1 — Baseline Verification (pre-change)

**Goal:** Confirm the current vulnerable state matches the spec's description before making any change, so the "before" behavior is established.

**Steps:**
1. Start the app: `uv run backend/app/main.py`, confirm listening on `http://localhost:3001`.
2. Run `curl -i http://localhost:3001/download/db` with no session/cookie.
   - Expected (pre-fix, current behavior): `HTTP/1.1 200 OK`, the raw SQLite file is returned, `content-disposition` names `vulnerable_app.db`.
3. Confirm in source that `download_db()` (`backend/app/api/routes/auth.py`, current lines 53–57) takes no `Request` parameter and performs no session check:
   ```python
   @router.get("/download/db")
   def download_db():
       # VULN-6: Exposed Database (intentional). No auth check whatsoever --
       # anyone who knows this URL can download the entire SQLite file.
       return FileResponse(DB_PATH, filename="vulnerable_app.db")
   ```
4. Confirm `welcome_page()` (current lines 83–94) already has the target pattern to mirror:
   ```python
   @router.get("/welcome")
   def welcome_page(request: Request):
       if "user_id" not in request.session:
           return RedirectResponse(url="/login", status_code=302)
       ...
   ```

No code is modified in this phase — it only establishes the baseline referenced by AC-01/AC-02 in the spec.

---

## Phase 2 — Implement the Session Check on `download_db()`

**Goal:** Apply FR-01 through FR-04 and NFR-01/NFR-03/NFR-04 from the spec.

**File:** `backend/app/api/routes/auth.py`

**Exact signature change:**

Before:
```python
@router.get("/download/db")
def download_db():
```

After:
```python
@router.get("/download/db")
def download_db(request: Request):
```

`Request` is already imported at the top of the file (`from fastapi import APIRouter, Form, Request`) — no new import needed (NFR-03).

**Exact session-check + redirect logic** (mirrors `welcome_page()` verbatim, per NFR-01):

```python
@router.get("/download/db")
def download_db(request: Request):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=302)

    # VULN-6 remediated: session-presence check gates access. Any
    # authenticated user may still download the file -- this app has no
    # role/admin system, so this is "authenticated only," not "admin only".
    # See .claude/specs/exposed-database-fix.md.
    return FileResponse(DB_PATH, filename="vulnerable_app.db")
```

Notes on the diff:
- The check is placed as the first statement in the function body, before any reference to `DB_PATH` or `FileResponse` construction (FR-02: no `FileResponse` is constructed on the unauthenticated path).
- `RedirectResponse` is already imported (`from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse`) — no new import needed.
- The old one-line VULN-6 comment ("No auth check whatsoever...") is replaced with a short comment noting the remediation and pointing at the spec, consistent with how the VULN-2 remediation in `welcome_page()` is commented in the same file.
- No other line in the function changes: `FileResponse(DB_PATH, filename="vulnerable_app.db")` is preserved exactly (NFR-02).
- No other route, import, or helper (`_read_template`, `index`, `signup_page`, `signup_post`, `login_page`, `login_post`, `search_user`, `logout`) is touched (NFR-04, and preserves VULN-3/VULN-7/VULN-8 intentionally unfixed elsewhere in the file).

---

## Phase 3 — Static Review Against Spec Requirements

**Goal:** Before running the app, verify the diff satisfies every FR/NFR without side effects.

**Checklist:**
- [ ] FR-01: `download_db()` checks `"user_id" not in request.session` — same key, same presence-check idiom as `welcome_page()`.
- [ ] FR-02: Unauthenticated path returns `RedirectResponse(url="/login", status_code=302)` and never reaches the `FileResponse(...)` line.
- [ ] FR-03: Authenticated path's `FileResponse(DB_PATH, filename="vulnerable_app.db")` call is byte-for-byte unchanged from before.
- [ ] FR-04: No role/permission/admin field referenced anywhere in the diff — only `"user_id"` in session.
- [ ] NFR-01: Conditional text is identical in form to `welcome_page()`'s (`if "user_id" not in request.session:`).
- [ ] NFR-03: No new imports added; only `Request` and `RedirectResponse`, both already present in the file's import block.
- [ ] NFR-04: `git diff` (once implemented) touches only the `download_db()` function — no changes to `/search`, `/welcome`, `/signup`, `/login`, `/logout`, `main.py`, `auth_service.py`, `security.py`, or `session.py`.

---

## Phase 4 — Functional Verification (post-change)

**Goal:** Execute the verification steps from `.claude/specs/exposed-database-fix.md` §10 against the modified code.

1. **Restart the app** to load the change:
   ```
   uv run backend/app/main.py
   ```
   Confirm it is listening at `http://localhost:3001`.

2. **Unauthenticated download is blocked (TC-01, AC-01):**
   ```
   curl -i http://localhost:3001/download/db
   ```
   Expected: `HTTP/1.1 302 Found` with a `location: /login` header, and no database file content in the body.

3. **Authenticated download still works (TC-02, AC-02):**
   - Register a user via the signup form at `http://localhost:3001/signup`.
   - Log in via `http://localhost:3001/login`, capturing the session cookie (browser devtools, or `curl -c cookies.txt` against `POST /login` with valid `username`/`password` form fields).
   - Request the file with the captured session:
     ```
     curl -i -b cookies.txt http://localhost:3001/download/db -o vulnerable_app_downloaded.db
     ```
   Expected: `HTTP/1.1 200 OK`, `content-disposition` header naming `vulnerable_app.db`, and the downloaded file is a valid SQLite database matching the server's live `vulnerable_app.db`.

4. **Session-missing and expired-session cases (TC-03, TC-04, EC-01–EC-03):**
   - Send a request with a cookie that lacks `user_id` (e.g., a hand-crafted or corrupted session cookie) — expect 302 to `/login`.
   - Send a request with a session older than `max_age=1800` seconds — expect 302 to `/login`.

5. **Residual "any authenticated user" behavior is present and expected, not a regression (TC-05, EC-04):**
   - Register a second user (User B), log in as User B, and confirm `GET /download/db` still succeeds with 200 and returns the full database (including User A's row). This is documented, intentional residual exposure per spec §2 — not a defect to fix here.

6. **Other vulnerabilities unaffected (TC-06, AC-04):**
   ```
   curl "http://localhost:3001/search?q=<script>alert(1)</script>"
   ```
   Expected: payload reflected unescaped (VULN-3 still present, unchanged).
   ```
   curl -i http://localhost:3001/welcome
   ```
   Expected: unauthenticated request redirects to `/login`, exactly as before this fix.
   - Confirm no rate-limiting or CSRF middleware has been added to `main.py` (VULN-7, VULN-8 untouched).

7. **Code-pattern check (AC-03, NFR-01):**
   Inspect the final `backend/app/api/routes/auth.py` and confirm `download_db()`'s conditional is textually identical in form to `welcome_page()`'s, and that no role/permission/admin concept was introduced anywhere in the file.

---

## Phase 5 — Documentation Follow-Up (out of code scope, noted for completeness)

Not part of this plan's code change, but flagged for a separate step after implementation lands, consistent with how prior remediations (VULN-1, VULN-2, VULN-4, VULN-5) were documented:

- Update `CLAUDE.md`'s Vulnerability Map and Important Rules to mark VULN-6 as remediated, referencing `.claude/specs/exposed-database-fix.md`, and to add a "never remove the session check on `/download/db`" rule alongside the existing VULN-1/VULN-2/VULN-4/VULN-5 rules.
- Update `README.md` if it enumerates vulnerability status (consistent with prior remediation commits per git history).

This phase is documentation-only and is called out here so it is not forgotten in the eventual implementation step — this plan does not perform it.

---

## Rollback Plan

If Phase 4 verification fails (e.g., authenticated download breaks), revert the single-function change in `backend/app/api/routes/auth.py` via `git checkout -- backend/app/api/routes/auth.py` (or equivalent), restoring the unauthenticated `download_db()`. No other file requires rollback since none other is touched.
