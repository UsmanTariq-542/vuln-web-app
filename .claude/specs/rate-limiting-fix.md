# Software Specification Document (Remediation Addendum)

## Vulnerable Web Application — Rate Limiting Fix (VULN-7)

**Version:** 1.0.0
**Companion Documents:** `docs/PRD.md`, `docs/TDD.md`, `.claude/specs/app-foundation.md`

---

## 1. Overview / Purpose

The application currently registers no throttling of any kind on any endpoint — `backend/app/main.py` contains only a comment noting the omission (`# VULN-7: No Rate Limiting (intentional, by omission)`). This means `POST /login` and `POST /signup`, the two endpoints that accept a username/password pair, can be hit an unlimited number of times per second from a single client, enabling unthrottled password brute-forcing against a known username and unthrottled username-enumeration/account-creation abuse. This document specifies the remediation of **VULN-7 (No Rate Limiting)**: adding the `slowapi` library — an in-memory, per-client-IP token-bucket limiter built on the `limits` package — and applying a request-rate limit to `login_post()` and `signup_post()` in `backend/app/api/routes/auth.py` only, leaving every other route in the application unthrottled, exactly as it is today.

---

## 2. Scope & Non-Goals

**In scope:** This document closes **VULN-7 only**. It adds `slowapi` as a dependency, wires a `Limiter` instance into the FastAPI app (`app.state.limiter`) with a `RateLimitExceeded` exception handler in `backend/app/main.py`, and applies a `@limiter.limit(...)` decorator to `login_post()` and `signup_post()` in `backend/app/api/routes/auth.py`.

**Out of scope / explicitly not touched:**

- **VULN-2** (Stored XSS) — already remediated per `.claude/specs/stored-xss-fix.md`. Not touched by this document.
- **VULN-3** (Reflected XSS / SQL Injection / exception leakage in `/search`) — already remediated per `.claude/specs/reflected-xss-fix.md`. Not touched by this document.
- **VULN-6** (Exposed Database) — already remediated per `.claude/specs/exposed-database-fix.md`. Not touched by this document.
- **VULN-8** (CSRF) — remains intentionally unfixed. Not touched by this document.
- **VULN-1, VULN-4, VULN-5** — already remediated in prior work, unrelated to this fix, and not touched by this document.

**Scope is auth endpoints only:** Only `POST /login` and `POST /signup` are rate-limited. `GET /welcome`, `GET /search`, `GET /download/db`, `GET /logout`, and every other route (`GET /`, `GET /signup`, `GET /login`) remain completely unthrottled, unchanged from current behavior. `/login` and `/signup` are the two routes that accept credentials/account-creation data and are therefore the brute-force and enumeration surface this fix targets; the other routes either serve static/template content, require an existing session, or (in `/search`'s and `/download/db`'s case) are separately-scoped vulnerabilities/fixes not affected by request volume in the way credential-guessing endpoints are.

**Known limitation — in-memory, single-process limiter (non-goal, stated explicitly):** `slowapi`'s default storage backend (used by this fix, via the `limits` package) keeps rate-limit counters **in the memory of the single running process**. This is appropriate for this application's lab/demo deployment model — one `uvicorn` process, run locally for a single student or small group — but it is explicitly **not a production-grade distributed rate limiter**. Specifically, and out of scope for this fix:

- Counters are **not shared across multiple worker processes or replicas**. If the app were ever run with multiple Uvicorn/Gunicorn workers or behind a horizontally-scaled deployment, each process would track its own independent counter, and the effective limit would be the configured limit multiplied by the number of processes.
- Counters are **reset on every process restart** — an attacker who can trigger or wait out a server restart gets a fresh limit window.
- There is **no shared backend** (e.g. Redis) configured; `slowapi`/`limits` support one, but wiring a shared store is a separate, larger change and is not part of this fix.
- The limiter keys on **remote IP address** (`get_remote_address`), which is spoofable/shareable behind NAT or a proxy that doesn't forward a trustworthy client IP; no proxy-aware IP extraction (e.g. trusted `X-Forwarded-For` parsing) is added by this fix.

This fix closes the "zero throttling whatsoever" form of VULN-7, appropriate for the app's stated single-process, localhost, educational deployment model (per `CLAUDE.md`'s "must never be deployed to production" rule). It does not claim to defend against a distributed or highly resourced attacker.

---

## 3. Affected Files

| File | Change |
|---|---|
| `backend/pyproject.toml` | Add `slowapi` to `[project].dependencies`. |
| `pyproject.toml` (project root) | Add `slowapi` to `[project].dependencies`. |
| `backend/app/main.py` | Instantiate a `Limiter` keyed by remote address, attach it to `app.state.limiter`, and register `slowapi`'s `_rate_limit_exceeded_handler` for the `RateLimitExceeded` exception. |
| `backend/app/api/routes/auth.py` | Apply a `@limiter.limit("5/minute")` decorator to `login_post()` and `signup_post()`. `signup_post()` gains a `request: Request` parameter (required by `slowapi` to inspect the incoming request); `login_post()` already has one. |

No other file is created, modified, or deleted by this fix (no new route, no new template, no DB schema change, no change to `auth_service.py` or `security.py`).

---

## 4. Functional Requirements

### FR-01: Limiter Dependency Added
`slowapi` must be added as a dependency in both `backend/pyproject.toml`'s and the root `pyproject.toml`'s `[project].dependencies` array, in the same list format already used by existing entries (a version-pinned string, e.g. `"slowapi>=0.1.9"`).

### FR-02: Limiter Instantiated and Attached to App State
`backend/app/main.py` must construct a `slowapi.Limiter` instance keyed by `slowapi.util.get_remote_address` (per-client-IP keying) and assign it to `app.state.limiter`, so route-level `@limiter.limit(...)` decorators can resolve it.

### FR-03: Rate-Limit-Exceeded Handler Registered
`backend/app/main.py` must register `slowapi.errors.RateLimitExceeded` with `app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)` (slowapi's built-in handler), so that a throttled request returns a `429` response with a JSON body instead of an unhandled server exception / generic `500`.

### FR-04: Login Endpoint Rate-Limited
`login_post()` in `backend/app/api/routes/auth.py` must be decorated with `@limiter.limit("5/minute")`, limiting each distinct client IP to 5 `POST /login` requests per rolling/fixed 60-second window (per `slowapi`/`limits` default window semantics).

### FR-05: Signup Endpoint Rate-Limited
`signup_post()` in `backend/app/api/routes/auth.py` must be decorated with `@limiter.limit("5/minute")`, with the same limit and rationale as FR-04. Because `slowapi` requires the decorated route function to accept a `Request` parameter, `signup_post()`'s signature gains `request: Request` as a parameter (unused by the function body itself, present solely so the decorator can inspect the request).

### FR-06: No Limiting on Non-Auth Routes
No other route (`GET /`, `GET /signup`, `GET /login`, `GET /welcome`, `GET /search`, `GET /download/db`, `GET /logout`) is decorated with `@limiter.limit(...)` or otherwise throttled by this fix. Their behavior under repeated/rapid requests is unchanged from current (unthrottled) behavior.

### FR-07: Throttled Response Shape
A request that exceeds the configured limit on `/login` or `/signup` must receive an HTTP `429 Too Many Requests` response with a JSON body (slowapi's default `_rate_limit_exceeded_handler` body, e.g. `{"error": "Rate limit exceeded: 5 per 1 minute"}` or equivalent), not an unhandled exception, stack trace, or `500`.

### FR-08: No Unrelated Vulnerability Fixes
This change must not modify `auth_service.py`'s query logic (VULN-1, already fixed), `security.py`'s hashing (VULN-5, already fixed), `/search`'s query/escaping (VULN-3, already fixed), `/download/db`'s session check (VULN-6, already fixed), `/welcome`'s escaping (VULN-2, already fixed), or add CSRF tokens/middleware (VULN-8, remains unfixed).

---

## 5. Non-Functional Requirements

### NFR-01: Limit Value and Rationale
The rate limit applied to both `login_post()` and `signup_post()` is **5 requests per minute per client IP**. Rationale: 5/minute is generous enough that a legitimate user who mistypes a password a few times, or briefly double-submits a signup form, is not locked out during normal use, while still reducing a brute-force/credential-stuffing or mass-account-creation attempt from thousands of attempts per minute down to 5 — a large enough reduction to meaningfully raise the cost of automated abuse in this lab context, without requiring a CAPTCHA, account lockout, or other heavier mechanism (those remain out of scope; see `docs/TDD.md`'s "No Rate Limiting" learning-objective note on defense-in-depth options beyond this fix).

### NFR-02: In-Memory, Single-Process Storage
The limiter must use `slowapi`'s/`limits`'s default in-memory storage backend (no external store such as Redis is configured). This is an explicit, documented limitation (see §2) appropriate to the app's single-process, localhost, educational deployment model — not a production-scale guarantee.

### NFR-03: Per-Client-IP Keying
The limiter must key on remote client IP address (`get_remote_address`), consistent with `slowapi`'s standard usage pattern. Proxy-aware IP resolution (trusted `X-Forwarded-For` parsing) is out of scope.

### NFR-04: Minimal Diff
The change is limited to: the two `pyproject.toml` dependency lists, the `Limiter`/exception-handler wiring in `main.py`, and the two `@limiter.limit(...)` decorators (plus `signup_post()`'s added `request: Request` parameter) in `auth.py`. No other function, route, or file is modified.

### NFR-05: No Change to Non-Throttled Response Behavior
For requests that stay within the limit, response payloads, status codes, and redirect targets for `login_post()` and `signup_post()` must remain identical in structure and content to their pre-fix behavior — the only observable change is that the 6th-and-beyond request within a given client's one-minute window now receives `429` instead of being processed.

---

## 6. Success Paths

**SP-01 — Login within the limit**: a client submits `POST /login` 1–5 times within a rolling minute. Every request is processed normally (existing `200`/`401` JSON responses per `auth_service.login()`'s existing logic) — none are throttled.

**SP-02 — Signup within the limit**: a client submits `POST /signup` 1–5 times within a rolling minute. Every request is processed normally (existing redirect/failure-page behavior per `auth_service.signup()`'s existing logic) — none are throttled.

**SP-03 — Throttled request returns 429**: a client submits a 6th `POST /login` (or `POST /signup`) request within the same one-minute window as its prior 5. The request is rejected with `429 Too Many Requests` and a JSON error body, without reaching `auth_service.login()`/`auth_service.signup()` at all.

**SP-04 — Limit resets after the window rolls over**: after waiting for the rate-limit window to elapse (per `slowapi`/`limits` window semantics for a `"5/minute"` limit), the same client can once again successfully submit `POST /login`/`POST /signup` requests, up to the limit again.

**SP-05 — Independent limits per client**: two different client IPs each get their own independent 5-per-minute allowance — one client exhausting its limit does not throttle a different client's requests to the same endpoint.

---

## 7. Edge Cases

**EC-01 — Rapid successive failed login attempts (brute force)**: an attacker submits 5 `POST /login` requests with varying passwords for a known username within a minute, then a 6th — the 6th (and any further attempts that minute) receives `429`, regardless of whether the attempted password would otherwise have succeeded.

**EC-02 — Non-auth routes remain unthrottled during a login/signup rate-limit window**: while a client is being throttled on `/login`, the same client's requests to `/welcome`, `/search`, `/download/db`, `/logout`, `/`, `GET /login`, or `GET /signup` are unaffected — none of those routes are decorated with a limiter and none return `429`.

**EC-03 — Limit is per-endpoint, not shared between `/login` and `/signup`**: a client that has exhausted its 5/minute `/login` allowance can still submit up to 5 `/signup` requests in that same window (each decorated route enforces its own independent counter under `slowapi`'s default per-route keying), unless the spec is later revised to share a bucket — this fix does not share counters between the two routes.

**EC-04 — Process restart resets all counters**: if the application process is restarted, all in-memory rate-limit counters are cleared — a client that was previously throttled gets a fresh allowance immediately after restart. This is a direct consequence of the in-memory storage limitation documented in §2 and is not treated as a defect of this fix.

**EC-05 — Multiple clients behind the same IP (e.g. shared NAT/campus network)**: because the limiter keys on remote IP address, multiple distinct users behind a shared public IP share one rate-limit bucket per route — one user's failed attempts can throttle another user behind the same IP. This is a known consequence of IP-based keying (documented in §2) and is not addressed by this fix.

**EC-06 — Throttled response is well-formed, not a crash**: a throttled request must never surface as an unhandled exception, Python traceback, or generic FastAPI `500` — `RateLimitExceeded` is caught by the registered handler and converted to a clean `429` JSON response.

---

## 8. Acceptance Criteria

**AC-01**: Given `backend/pyproject.toml` and the root `pyproject.toml`, when reviewed, then both list `slowapi` in `[project].dependencies` using the existing version-pinned string format.

**AC-02**: Given `backend/app/main.py`, when reviewed, then a `Limiter` instance keyed by `get_remote_address` is assigned to `app.state.limiter`, and `RateLimitExceeded` is registered with `_rate_limit_exceeded_handler` via `app.add_exception_handler(...)`.

**AC-03**: Given `backend/app/api/routes/auth.py`, when reviewed, then both `login_post()` and `signup_post()` are decorated with `@limiter.limit("5/minute")`, and `signup_post()` has gained a `request: Request` parameter.

**AC-04**: Given a client that submits 5 `POST /login` requests within a minute, when a 6th is submitted within that same window, then the response is `429` with a JSON error body, and `auth_service.login()` is not invoked for that 6th request.

**AC-05**: Given a client throttled on `/login`, when it requests `GET /welcome`, `GET /search`, `GET /download/db`, or `GET /logout` in the same window, then none of those requests are throttled — all behave exactly as before this fix.

**AC-06**: Given a throttled client, when it waits until the one-minute window has elapsed and submits another `POST /login`/`POST /signup` request, then the request is processed normally (not `429`), subject to the existing 5-per-window allowance resetting.

**AC-07**: Given any request to `/login` or `/signup` that stays within the 5-per-minute limit, when compared to pre-fix behavior, then its response status code and body are unchanged.

**AC-08**: Vulnerability #7 (No Rate Limiting) is considered fixed for `/login` and `/signup`.

**AC-09**: Vulnerabilities #2, #3, #6, #8 remain intentionally unchanged by this document; `auth_service.py` and `security.py` are byte-for-byte unchanged.

---

## 9. Test Cases

| ID | Scenario | Precondition | Expected Result |
|---|---|---|---|
| TC-01 | 6th `/login` attempt within a minute is throttled | Same client IP; no prior requests this window | Submit 5 `POST /login` requests (any credentials) within 60 seconds, then a 6th immediately after → 6th returns `429` with a JSON error body; `auth_service.login()` is never reached for request 6 |
| TC-02 | Request after the window rolls over succeeds again | Client has been throttled (6th request returned `429`) | Wait until the 60-second window has elapsed, then submit another `POST /login` → request is processed normally (`200` or `401` per credentials), not `429` |
| TC-03 | `/welcome` remains unthrottled | Client has exhausted its `/login` rate limit in the current window | `GET /welcome` (with or without a valid session) → behaves exactly as before this fix (session-gated redirect or dashboard content), never `429` |
| TC-04 | `/search` remains unthrottled | Client has exhausted its `/login` rate limit in the current window | Repeated `GET /search?q=test` requests (more than 5 in a minute) → all return `200` normally, never `429` |
| TC-05 | 6th `/signup` attempt within a minute is throttled | Same client IP; no prior requests this window | Submit 5 `POST /signup` requests within 60 seconds, then a 6th → 6th returns `429`; `auth_service.signup()` is never reached for request 6 |
| TC-06 | `/login` and `/signup` limits are independent | Client has exhausted its `/login` limit this window | `POST /signup` (fresh data) still succeeds up to its own 5-per-minute allowance in the same window |
| TC-07 | Successful login within the limit is unaffected | Registered user; fewer than 5 prior `/login` requests this window | Correct credentials submitted → `200`/JSON `{"success": true, "redirect": "/welcome"}`, identical to pre-fix behavior |
| TC-08 | Two different client IPs have independent limits | Two distinct source IPs available (or simulated) | Client A exhausts its 5/minute `/login` limit; Client B's `/login` requests in the same window are unaffected |
| TC-09 | `/download/db` and `/logout` remain unthrottled | Client has exhausted its `/login` rate limit in the current window | `GET /download/db` and `GET /logout` behave exactly as before this fix, never `429` |

---

## 10. Verification Steps

1. Install the new dependency:
   ```
   cd backend && uv sync
   ```
2. Start the application from the project root:
   ```
   uv run backend/app/main.py
   ```
   Confirm it is listening at `http://localhost:3001`.

3. **6th `/login` attempt is throttled (TC-01, AC-04):**
   ```
   for i in 1 2 3 4 5 6; do
     curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:3001/login \
       -d "username=nonexistent" -d "password=wrong"
   done
   ```
   Expected: the first 5 lines print `401` (invalid credentials, normal behavior); the 6th prints `429`.

4. **Window rollover restores access (TC-02, AC-06):**
   Wait 60+ seconds after the throttled request in step 3, then repeat a single request:
   ```
   curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:3001/login \
     -d "username=nonexistent" -d "password=wrong"
   ```
   Expected: `401` (processed normally, not `429`).

5. **`/welcome` and `/search` remain unthrottled (TC-03, TC-04, AC-05):**
   Immediately after exhausting the `/login` limit (before the window resets), run:
   ```
   curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3001/welcome
   for i in 1 2 3 4 5 6 7; do
     curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:3001/search?q=test"
   done
   ```
   Expected: `/welcome` returns `302` (redirect to `/login`, unauthenticated — unrelated to rate limiting); all `/search` requests return `200`, none return `429`.

6. **6th `/signup` attempt is throttled (TC-05, AC-03):**
   ```
   for i in 1 2 3 4 5 6; do
     curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:3001/signup \
       -d "username=user$i" -d "email=user$i@example.com" -d "password=Password123"
   done
   ```
   Expected: the first 5 requests process normally (`302` redirect to `/login` on success, or a failure page for duplicates); the 6th returns `429`.

7. **`/login` and `/signup` limits are independent (TC-06):**
   After exhausting `/login`'s limit (step 3), confirm a fresh `POST /signup` still succeeds (subject to its own 5-per-minute allowance):
   ```
   curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:3001/signup \
     -d "username=independenttest" -d "email=independenttest@example.com" -d "password=Password123"
   ```
   Expected: `302` (not `429`), assuming `/signup`'s own limit has not separately been exhausted.

8. **Source-level check (AC-01, AC-02, AC-03):**
   - Inspect `backend/pyproject.toml` and the root `pyproject.toml` — confirm `slowapi` is listed in `dependencies`.
   - Inspect `backend/app/main.py` — confirm `Limiter(key_func=get_remote_address)` (or equivalent) is assigned to `app.state.limiter`, and `RateLimitExceeded` is registered with `_rate_limit_exceeded_handler`.
   - Inspect `backend/app/api/routes/auth.py` — confirm `@limiter.limit("5/minute")` decorates both `login_post()` and `signup_post()`, and `signup_post()` has a `request: Request` parameter.

9. **Other vulnerabilities unaffected (AC-09):**
   ```
   git diff -- backend/app/services/auth_service.py backend/app/core/security.py
   ```
   Expected: no output (no changes).
   ```
   curl -i http://localhost:3001/download/db
   ```
   Expected: unauthenticated request redirects to `/login` (VULN-6 remediation, unchanged).
