# Implementation Plan

## Reflected XSS Fix (VULN-3)

**Version:** 1.0.0
**Source Spec:** `.claude/specs/reflected-xss-fix.md`
**Companion Documents:** `docs/PRD.md`, `docs/TDD.md`, `.claude/specs/app-foundation.md`, `.claude/specs/sql-injection-fix.md`

---

## 0. Plan Scope

This plan implements only what `.claude/specs/reflected-xss-fix.md` specifies: fixing all three issues bundled into `search_user()` in `backend/app/api/routes/auth.py` — the string-concatenated SQL query, the unescaped reflection of `q` and result rows, and the raw exception-message leakage. It does **not** touch:

- `backend/app/services/auth_service.py` (VULN-1's already-parameterized `signup()`/`login()` queries — a separate query in a separate file, explicitly out of scope per the spec's §2)
- `backend/app/core/security.py` (bcrypt — VULN-5 remediation, untouched)
- `backend/app/main.py` (`SECRET_KEY` sourcing, `SessionMiddleware` config — VULN-4 remediation, untouched)
- `backend/app/db/session.py` (`get_db()`/`init_db()`, schema — untouched)
- Any other route in `auth.py` (`index`, `signup_page`, `signup_post`, `login_page`, `login_post`, `download_db`, `welcome_page`, `logout`)
- Any rate-limiting or CSRF middleware (VULN-7, VULN-8 remain absent/unfixed)

Single file touched by the implementation phase: `backend/app/api/routes/auth.py`, and within it, only `search_user()`. This plan document itself makes no code changes.

---

## Phase 1 — Baseline Verification (pre-change)

**Goal:** Confirm the current vulnerable state matches the spec's description before making any change.

**Steps:**
1. Start the app: `uv run backend/app/main.py`, confirm listening on `http://localhost:3001`.
2. Run `curl -s "http://localhost:3001/search?q=<script>alert(1)</script>"`.
   - Expected (pre-fix, current behavior): the raw `<script>alert(1)</script>` tag appears unescaped in the `<h2>` heading.
3. Run `curl -s "http://localhost:3001/search?q=' OR '1'='1"`.
   - Expected (pre-fix): the `OR '1'='1'` clause alters the SQL query, likely returning every row in the `users` table.
4. Confirm in source that `search_user()` (`backend/app/api/routes/auth.py`, current lines 65–85) builds its query via string concatenation, embeds `q`/rows unescaped, and leaks exception text:
   ```python
   @router.get("/search")
   def search_user(q: str = ""):
       # VULN-3: Reflected XSS (intentional), plus SQL Injection via string
       # concatenation, plus raw exception-message leakage. None of the three
       # are accidental -- do not parameterize the query or escape the output.
       try:
           conn = get_db()
           query = (
               "SELECT username, email FROM users WHERE username LIKE '%" + q
               + "%' OR email LIKE '%" + q + "%'"
           )
           rows = conn.execute(query).fetchall()
           conn.close()

           results_html = "".join(
               f"<li>{row['username']} ({row['email']})</li>" for row in rows
           )
           body = f"<h2>Search results for: {q}</h2><ul>{results_html}</ul>"
           return HTMLResponse(body)
       except Exception as e:
           return HTMLResponse(f"<p>Search error: {e}</p>", status_code=500)
   ```
5. Confirm the reference parameterization pattern already established for VULN-1 in `backend/app/services/auth_service.py` (per `.claude/specs/sql-injection-fix.md`) uses `?` placeholders with a bound parameter tuple passed to `conn.execute(query, params)` — this is the style to mirror, applied to a different query in `auth.py`.
6. Confirm `html.escape()` is already imported at the top of `auth.py` (`import html`, line 1) and already used in `welcome_page()` for the VULN-2 fix — this is the escaping call to reuse, not a new import.

No code is modified in this phase — it only establishes the baseline referenced by AC-02/AC-03 in the spec.

---

## Phase 2 — Parameterize the Search Query

**Goal:** Apply FR-01, FR-02, NFR-01, NFR-02, NFR-03, NFR-04 from the spec.

**File:** `backend/app/api/routes/auth.py`, function `search_user()`.

**Exact query change** (mirrors `auth_service.py`'s `?`-placeholder + bound-tuple style):

Before:
```python
        conn = get_db()
        query = (
            "SELECT username, email FROM users WHERE username LIKE '%" + q
            + "%' OR email LIKE '%" + q + "%'"
        )
        rows = conn.execute(query).fetchall()
        conn.close()
```

After:
```python
        conn = get_db()
        like_pattern = f"%{q}%"
        rows = conn.execute(
            "SELECT username, email FROM users WHERE username LIKE ? OR email LIKE ?",
            (like_pattern, like_pattern),
        ).fetchall()
        conn.close()
```

Notes:
- The `%`-wildcard wrapping (`f"%{q}%"`) is built in Python and passed as a **parameter value**, never interpolated into the query **text** — this satisfies FR-01/FR-02 (query text is a fixed string; only bound values vary).
- The same `like_pattern` value is bound to both placeholders, matching the original query's behavior of applying the same `%q%` pattern to both the `username` and `email` `LIKE` comparisons.
- `get_db()` and `conn.close()` usage is otherwise unchanged (NFR-03: same connection pattern as the rest of the codebase).
- No new import is required (`conn.execute` already accepts a `params` tuple as used by `auth_service.py`).

---

## Phase 3 — HTML-Escape `q` and Result Row Fields

**Goal:** Apply FR-03, FR-04 from the spec, reusing the exact `html.escape()` call already used in `welcome_page()` for VULN-2.

**File:** `backend/app/api/routes/auth.py`, function `search_user()`.

**Exact escaping change:**

Before:
```python
        results_html = "".join(
            f"<li>{row['username']} ({row['email']})</li>" for row in rows
        )
        body = f"<h2>Search results for: {q}</h2><ul>{results_html}</ul>"
        return HTMLResponse(body)
```

After:
```python
        results_html = "".join(
            f"<li>{html.escape(row['username'])} ({html.escape(row['email'])})</li>"
            for row in rows
        )
        body = f"<h2>Search results for: {html.escape(q)}</h2><ul>{results_html}</ul>"
        return HTMLResponse(body)
```

Notes:
- `html.escape(q)` covers FR-03 (escaped reflection of `q` in the `<h2>` heading).
- `html.escape(row['username'])` and `html.escape(row['email'])` cover FR-04 (escaped result-row fields), applied to *every* row regardless of whether the stored value happens to contain markup (EC-03/TC-06 — a username stored with markup, from any source, still renders escaped here).
- `html` is already imported at the top of the file; no new import.
- The overall HTML structure (`<h2>...</h2><ul>...</ul>` with `<li>` rows) is unchanged — only the values placed inside are now escaped (FR-06: response shape preserved).

---

## Phase 4 — Replace the Exception Handler's Leaking Response

**Goal:** Apply FR-05, NFR-04 from the spec.

**File:** `backend/app/api/routes/auth.py`, function `search_user()`.

**Exact replacement error-handling body:**

Before:
```python
    except Exception as e:
        return HTMLResponse(f"<p>Search error: {e}</p>", status_code=500)
```

After:
```python
    except Exception:
        return HTMLResponse("<p>Search error. Please try again.</p>", status_code=500)
```

Notes:
- The exception is no longer bound to a name (`except Exception:` instead of `except Exception as e:`) since it is never referenced in the response — this by construction prevents any future accidental reintroduction of `{e}` interpolation in this block.
- The message is a fixed string literal, not an f-string — no exception object, class name, file path, or traceback fragment can leak into it (NFR-04).
- `status_code=500` is preserved unchanged (FR-05: still a `500`, only the body content changes).

---

## Phase 5 — Full Post-Change Function (for review)

**Goal:** Show the complete resulting `search_user()` body so the diff can be reviewed as a whole before implementation, combining Phases 2–4.

```python
@router.get("/search")
def search_user(q: str = ""):
    # VULN-3 remediated: query is parameterized (?-placeholder binding, same
    # pattern as auth_service.py's VULN-1 fix), q and result-row fields are
    # HTML-escaped before embedding, and the exception handler no longer
    # leaks exception detail. See .claude/specs/reflected-xss-fix.md.
    try:
        conn = get_db()
        like_pattern = f"%{q}%"
        rows = conn.execute(
            "SELECT username, email FROM users WHERE username LIKE ? OR email LIKE ?",
            (like_pattern, like_pattern),
        ).fetchall()
        conn.close()

        results_html = "".join(
            f"<li>{html.escape(row['username'])} ({html.escape(row['email'])})</li>"
            for row in rows
        )
        body = f"<h2>Search results for: {html.escape(q)}</h2><ul>{results_html}</ul>"
        return HTMLResponse(body)
    except Exception:
        return HTMLResponse("<p>Search error. Please try again.</p>", status_code=500)
```

The old top-of-function comment ("VULN-3: Reflected XSS (intentional)... do not parameterize the query or escape the output") is replaced with a short remediation note pointing at the spec, consistent with how the VULN-2 and VULN-6 remediations are commented elsewhere in this same file.

---

## Phase 6 — Static Review Against Spec Requirements

**Goal:** Before running the app, verify the diff satisfies every FR/NFR without side effects.

**Checklist:**
- [ ] FR-01/FR-02: query text is a fixed string with two `?` placeholders; no `q`-derived value appears in the query text itself, only in the bound `(like_pattern, like_pattern)` tuple.
- [ ] FR-03: `q` is passed through `html.escape()` before appearing in the `<h2>` heading.
- [ ] FR-04: both `row['username']` and `row['email']` are passed through `html.escape()` before appearing in each `<li>`.
- [ ] FR-05: the `except` block's response body is a fixed generic string with no exception interpolation.
- [ ] FR-06: route method (`GET`), path (`/search`), query-param name (`q`), default (`""`), and response type (`HTMLResponse` fragment with `<h2>`/`<ul>`/`<li>` structure) are all unchanged.
- [ ] FR-07 / NFR-05: `git diff` (once implemented) touches only `search_user()` inside `backend/app/api/routes/auth.py` — no changes to `auth_service.py`, `security.py`, `main.py`, `session.py`, or any other route.
- [ ] NFR-01: no raw `q` value is interpolated, formatted, or concatenated into SQL text.
- [ ] NFR-02: parameterization uses the same `?`-placeholder + tuple-binding pattern as `auth_service.py`'s VULN-1 fix; escaping uses the same `html.escape()` call as `welcome_page()`'s VULN-2 fix — no new library introduced.
- [ ] NFR-03: no new dependency added to `backend/pyproject.toml` or root `pyproject.toml`.
- [ ] NFR-04: no code path in `search_user()` can place exception text, class name, file path, or traceback into a response body.

---

## Phase 7 — Functional Verification (post-change)

**Goal:** Execute the verification steps from `.claude/specs/reflected-xss-fix.md` §10 against the modified code.

1. **Restart the app** to load the change:
   ```
   uv run backend/app/main.py
   ```
   Confirm it is listening at `http://localhost:3001`.

2. **Reflected XSS is neutralized (TC-01, AC-02):**
   ```
   curl -s "http://localhost:3001/search?q=<script>alert(1)</script>"
   ```
   Expected: response body contains `&lt;script&gt;alert(1)&lt;/script&gt;`; no literal `<script>` tag appears anywhere in the body.

3. **`<img onerror>` variant (TC-02):**
   ```
   curl -s "http://localhost:3001/search?q=<img src=x onerror=alert(1)>"
   ```
   Expected: the payload appears HTML-escaped, not as a live `<img>` tag.

4. **SQL injection no longer returns all rows (TC-03, AC-03):**
   ```
   curl -s "http://localhost:3001/search?q=' OR '1'='1"
   ```
   Expected: `200` response; the result list reflects a literal substring match (likely empty), not every user in the database; no `500`/stack trace.

5. **Zero-result search (TC-04, AC-04):**
   ```
   curl -s "http://localhost:3001/search?q=zzz_no_such_user_zzz"
   ```
   Expected: `200` with an empty `<ul></ul>`.

6. **Normal search still works (TC-05, AC-06):**
   - Register a user via `http://localhost:3001/signup` with a known username, e.g. `verifyuser`.
   - Request: `curl -s "http://localhost:3001/search?q=verifyuser"`.
   Expected: `200` with an `<li>` entry containing `verifyuser` and its email.

7. **Stored markup in a username renders escaped (TC-06):**
   - If a test account with markup in its username/email is available, search for a matching substring and confirm the markup appears escaped in the `<li>` output.

8. **Generic error on failure (TC-07, AC-05, NFR-04):**
   - Simulate a search-time failure (e.g. temporarily rename/lock the SQLite file, if feasible) and confirm the response is `500` with only the fixed generic message — no exception text, class name, or traceback in the body.

9. **Source-level parameterization check (AC-01):**
   Inspect `backend/app/api/routes/auth.py` and confirm `search_user()`'s query uses `?` placeholders with a bound parameter tuple, not string concatenation.

10. **`auth_service.py` untouched (AC-07, TC-09):**
    ```
    git diff -- backend/app/services/auth_service.py
    ```
    Expected: no output (no changes).

11. **Other vulnerabilities unaffected (AC-09):**
    ```
    curl -i http://localhost:3001/download/db
    ```
    Expected: unauthenticated request redirects to `/login` (VULN-6 remediation, unchanged by this fix).
    ```
    curl -i http://localhost:3001/welcome
    ```
    Expected: unauthenticated request redirects to `/login` (VULN-2/session behavior unchanged by this fix).

---

## Rollback Plan

If Phase 7 verification fails (e.g., normal search results break, or an unrelated route is affected), revert the single-function change in `backend/app/api/routes/auth.py` via `git checkout -- backend/app/api/routes/auth.py` (or equivalent), restoring the prior `search_user()`. No other file requires rollback since none other is touched.
