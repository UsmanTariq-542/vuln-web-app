# Software Specification Document (Remediation Addendum)

## Vulnerable Web Application — Exposed Database Fix (VULN-6)

**Version:** 1.0.0
**Companion Documents:** `docs/PRD.md`, `docs/TDD.md`, `.claude/specs/app-foundation.md`

---

## 1. Overview / Purpose

`GET /download/db` currently serves the raw SQLite database file (`vulnerable_app.db`) to any client that requests it, with no authentication check of any kind — this is VULN-6, Exposed Database, one of the 8 intentional vulnerabilities in the `v0.1.0` baseline. Because the file contains every user row, including bcrypt password hashes, any unauthenticated party who discovers or guesses the route can exfiltrate the entire user table. This document specifies the remediation: gating `/download/db` behind the same session-presence check already used by `welcome_page()` in `backend/app/api/routes/auth.py`, so that only requests carrying a valid, authenticated session may download the file. All other behavior of the route — what it serves, to whom once authenticated, and under what filename — is unchanged.

---

## 2. Scope & Non-Goals

**In scope:** This document closes **VULN-6 only**. It adds a session check to `download_db()` that mirrors the existing pattern in `welcome_page()`: if `"user_id"` is not present in `request.session`, the request is redirected to `/login` (302) instead of receiving the file.

**Out of scope / explicitly not touched:**

- **VULN-2** (Stored XSS) — already remediated per `.claude/specs/stored-xss-fix.md`. Not touched by this document.
- **VULN-3** (Reflected XSS / SQL Injection in `/search`) — remains intentionally unfixed. Not touched by this document.
- **VULN-7** (No Rate Limiting) — remains intentionally unfixed. Not touched by this document.
- **VULN-8** (CSRF) — remains intentionally unfixed. Not touched by this document.
- **VULN-1, VULN-4, VULN-5** — already remediated in prior work, unrelated to this route, and not touched by this document.

**Known limitation — no role/admin system (non-goal, stated explicitly):** This application has no role, permission, or admin concept anywhere in its design (see `docs/TDD.md` §3, `.claude/specs/app-foundation.md` §8 — the session state model stores only `user_id`, `username`, `email`, with no role field). Consequently, this fix cannot restrict database download to "administrators" — no such distinction exists in the system. The remediation is **"any authenticated user," not "admin only."** This means any user who successfully registers and logs in — using the same public, unauthenticated `/signup` endpoint available to anyone — can still download the full database, including every other user's row and password hash, once logged in. This is a real, acknowledged residual exposure and is **not** addressed by this document; building an authorization/role system to close it is a separate, larger change requiring its own spec and is intentionally out of scope here. This document closes only the "zero-authentication, fully public" form of VULN-6.

---

## 3. Affected Files

| File | Change |
|---|---|
| `backend/app/api/routes/auth.py` | `download_db()` gains a `Request` parameter and a session-presence check before the `FileResponse` is returned. |

No other file is created, modified, or deleted by this fix (no new route, no new template, no DB schema change, no new dependency).

---

## 4. Functional Requirements

### FR-01: Session Check on Download Route
`GET /download/db` must check for the presence of `"user_id"` in `request.session` before serving the database file, using the identical presence check already applied in `welcome_page()`.

### FR-02: Unauthenticated Redirect
If `"user_id"` is not present in the session, the route must return a 302 redirect to `/login`, and must not construct or return a `FileResponse` in that case.

### FR-03: Authenticated Pass-Through
If `"user_id"` is present in the session, the route's existing behavior is preserved exactly: it returns a `FileResponse` for `DB_PATH` with `filename="vulnerable_app.db"`, unchanged in content, headers, or filename.

### FR-04: No New Authorization Tier
The fix must not introduce a role, permission, or admin-only check. The sole gate is session presence, identical in kind to the gate already used on `/welcome`.

---

## 5. Non-Functional Requirements

### NFR-01: Pattern Consistency
The session check must reuse the exact conditional form already present in `welcome_page()` (`if "user_id" not in request.session:`) rather than introducing a new or differently-shaped auth-check idiom into the file.

### NFR-02: No Behavior Change for Authenticated Requests
Response latency, headers, streamed file content, and filename for an authenticated download must be identical, byte-for-byte, to current behavior — the only observable change is that unauthenticated requests no longer receive the file.

### NFR-03: No New Dependencies
The fix must be achievable using only `fastapi.Request` and `fastapi.responses.RedirectResponse`, both already imported in `auth.py`.

### NFR-04: Minimal Diff
The change must be limited to the `download_db()` function signature and body; no other route or helper in `auth.py` is modified.

---

## 6. Success Paths

**SP-01 — Authenticated download**: A user logs in, establishing a session containing `user_id`. They request `GET /download/db`. The session check passes, and the SQLite file is returned as an attachment named `vulnerable_app.db`.

**SP-02 — Unauthenticated request blocked**: A client with no session (or a session missing `user_id`) requests `GET /download/db`. The session check fails, and the client is redirected (302) to `/login` without ever receiving file bytes.

---

## 7. Edge Cases

**EC-01**: A request arrives with no session cookie at all (fresh browser) — treated identically to a missing `user_id`, redirected to `/login`.

**EC-02**: A request arrives with a session cookie present but not containing `user_id` (e.g., a corrupted or partially-cleared session) — redirected to `/login`, same as EC-01.

**EC-03**: A request arrives with an expired session (per the `max_age=1800` session-cookie policy from the VULN-4 remediation) — Starlette's `SessionMiddleware` treats an expired/invalid signed cookie as no session, so `user_id` is absent and the request is redirected to `/login`.

**EC-04**: An authenticated user (any registered account, not an "admin") requests the route — per the stated non-goal in §2, this succeeds and the file is served; this is expected, documented residual behavior, not a defect.

**EC-05**: The SQLite file is missing from disk at request time for an authenticated request — this is pre-existing `FileResponse` behavior (unchanged by this fix, since the session check only gates whether that code path is reached) and is out of scope for this document.

---

## 8. Acceptance Criteria

**AC-01 — Unauthenticated request redirected**: Given no session or a session lacking `user_id`, when `GET /download/db` is requested, then the response is a 302 redirect to `/login` and no file bytes are returned.

**AC-02 — Authenticated request unaffected**: Given a valid session containing `user_id`, when `GET /download/db` is requested, then the response is the SQLite database file with filename `vulnerable_app.db`, identical to current pre-fix behavior.

**AC-03 — No new authorization concept introduced**: Given the fixed route, when its implementation is inspected, then the only check present is session-presence (`"user_id" not in request.session`) — no role, permission, or admin field is referenced anywhere in the change.

**AC-04 — Other vulnerabilities untouched**: Given the fixed route, when `/search`, `/welcome`, and the absence of rate-limiting/CSRF middleware are inspected, then none of VULN-2, VULN-3, VULN-7, or VULN-8 show any behavioral change from this fix.

---

## 9. Test Cases

| ID | Scenario | Precondition | Expected Result |
|---|---|---|---|
| TC-01 | Unauthenticated download attempt | No prior login; no session cookie sent | `GET /download/db` returns 302 redirect to `/login`; no file bytes in response |
| TC-02 | Authenticated download succeeds | User has logged in and holds a valid session cookie | `GET /download/db` returns 200 with the SQLite file, `filename="vulnerable_app.db"`, content unchanged from pre-fix baseline |
| TC-03 | Session missing `user_id` | Session cookie present but does not contain `user_id` (e.g., manually cleared) | `GET /download/db` returns 302 redirect to `/login` |
| TC-04 | Expired session | Session cookie older than `max_age=1800` seconds | `GET /download/db` returns 302 redirect to `/login` |
| TC-05 | Any authenticated (non-admin) account can still download | Two distinct users exist; User B (not the "owner" of any special role) logs in | `GET /download/db` as User B returns 200 with the full database file, including User A's row — documented residual exposure per §2, not a test failure |
| TC-06 | `/welcome` and `/search` unaffected | Any session state | `/welcome` and `/search` behave exactly as before this fix (session-gated dashboard; unauthenticated, unescaped, SQL-concatenated search respectively) |

---

## 10. Verification Steps

1. Start the application from the project root:
   ```
   uv run backend/app/main.py
   ```
   Confirm it is listening at `http://localhost:3001`.

2. **Unauthenticated download is blocked (TC-01):**
   ```
   curl -i http://localhost:3001/download/db
   ```
   Expected: `HTTP/1.1 302 Found` with a `location: /login` header, and no database file content in the body.

3. **Authenticated download still works (TC-02):**
   - Register a user via the signup form at `http://localhost:3001/signup`.
   - Log in via `http://localhost:3001/login`, capturing the session cookie (e.g., via browser devtools, or `curl -c cookies.txt` against `POST /login` with valid `username`/`password` form fields).
   - Request the file with the captured session:
     ```
     curl -i -b cookies.txt http://localhost:3001/download/db -o vulnerable_app_downloaded.db
     ```
   Expected: `HTTP/1.1 200 OK`, `content-disposition` header naming `vulnerable_app.db`, and the downloaded file is a valid SQLite database matching the server's live `vulnerable_app.db`.

4. **Session-check code path matches `welcome_page()` (AC-03, NFR-01):**
   Inspect `backend/app/api/routes/auth.py` and confirm `download_db()` uses the identical conditional (`if "user_id" not in request.session:`) as `welcome_page()`, with no role/permission field referenced anywhere in the diff.

5. **Other vulnerabilities unaffected (AC-04, TC-06):**
   ```
   curl "http://localhost:3001/search?q=<script>alert(1)</script>"
   ```
   Expected: the payload is reflected unescaped in the HTML response (VULN-3 still present, unchanged).
   ```
   curl -i http://localhost:3001/welcome
   ```
   Expected: unauthenticated request redirects to `/login`, exactly as before this fix (VULN-2 remediation and session-gating on `/welcome` unchanged).
