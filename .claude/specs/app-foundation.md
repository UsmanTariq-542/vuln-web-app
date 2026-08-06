# Software Specification Document (Implementation Addendum)

## Vulnerable Web Application — App Foundation

**Version:** 1.0.0
**Companion Documents:** `docs/PRD.md`, `docs/TDD.md`

---

## 1. Scope

This document is an **implementation addendum** to `docs/PRD.md` and `docs/TDD.md`. It captures only the **implementation-level behavior** required to reproduce the application exactly — runtime behavior, user flows, functional requirements, the full visual design system, form/validation specifics, session-state and data-lifecycle rules, and acceptance/test criteria.

It intentionally **omits** material already covered by the companion documents:

- Product goals, target audience, roadmap, success metrics, risk assessment (see PRD §1–2, §7–9)
- System architecture, technology stack, component responsibilities (see TDD §2–3)
- The 8 intentional vulnerability descriptions and their OWASP mapping (see PRD §3.2, TDD §4)
- Database schema definition (see TDD §3.1.4, §11.3)
- Endpoint inventory (see TDD §3.1.2, §11.4)

A compliant implementation must satisfy this document **in addition to** the companion documents, not instead of them.

---

## 2. Runtime Behavior

- **Automatic database initialization**: on application startup, the database schema is created if it does not already exist. No manual migration step is required.
- **Missing DB file recreated automatically**: if the SQLite file is absent at startup (first run, or deleted by a user resetting their environment), it is recreated transparently with an empty `users` table.
- **Data preserved across restarts**: existing rows in the SQLite file are never dropped or reset by application startup; the "create if missing" check must not overwrite existing data.
- **Static assets available after boot**: CSS and image assets are served from disk without a build step; they must be reachable immediately once the server is listening, with no separate asset-compilation phase.
- **Templates loaded from disk at request time, no caching**: HTML templates are read from the filesystem on every request rather than cached in memory at startup. This means an edit to a template file takes effect on the very next request without an application restart.
- **Dashboard content modified via runtime string substitution**: the dashboard template is not rendered by a templating engine; a placeholder token in the raw HTML is replaced with the current user's username via straightforward string substitution before the response is returned.
- **Authentication state based solely on session presence**: there is no separate token, header, or database lookup used to gate protected routes at request time — the presence of the expected key(s) in the request's session object is the sole authorization check.

---

## 3. User Flows

### 3.1 Registration Flow

1. User navigates to the signup page; the registration form is rendered.
2. User fills in username, email, password, and password confirmation.
3. **Client-side validation** checks that password and confirm-password match before the form is allowed to submit. A mismatch blocks submission and shows an inline message; no request is sent to the server in this case.
4. On a matching pair, the browser performs a standard form submission (full page POST, not fetch) to the registration endpoint.
5. The server creates the new user record.
6. On success, the server issues a redirect to the login page.
7. On failure (e.g., username already taken), the server re-renders a page communicating the failure rather than completing the redirect.

### 3.2 Login Flow

1. User navigates to the login page; the login form is rendered.
2. User fills in username and password.
3. On submit, the page performs an **asynchronous `fetch()` request** to the login endpoint (not a full page POST) — the page does not reload at submission time.
4. The client JavaScript processes the JSON response:
   - On success, it triggers a client-side redirect to the dashboard.
   - On failure, it renders the returned error message inline on the login form without navigating away.
5. On successful authentication, the server has already established the session (user id, username, email) before returning its JSON response; the client redirect is purely a navigation step, not part of the authorization decision.

### 3.3 Dashboard Flow

1. A request arrives for the dashboard route.
2. The server checks the session for the expected authentication marker.
   - If absent, the request is redirected to the login page and no dashboard content is rendered.
3. If present, the dashboard template is loaded fresh from disk.
4. The current username is substituted into the template's placeholder token.
5. The completed HTML is returned to the client.

### 3.4 Logout Flow

1. User initiates logout (link/button on the dashboard).
2. The server clears all session data associated with the request.
3. The server redirects the client to the login page.
4. Any subsequent request to a protected resource (e.g., the dashboard) in the same browser is now treated as unauthenticated and redirected to login again — the cleared session leaves no residual access.

---

## 4. Functional Requirements

### FR-01: Session Management
The application must establish a server-side session upon successful authentication and must be able to fully clear that session on logout. Session data is the single source of truth for "is this request authenticated."

### FR-02: Dynamic User Context
Any page that needs to display information about the current user (e.g., the dashboard's username) must source that information from the active session at request time, not from a cached or precomputed value.

### FR-03: Route Protection
Routes designated as protected must verify session state before returning protected content, and must redirect unauthenticated requests to the login page rather than returning partial or error content.

### FR-04: Error Handling
Failure conditions (duplicate username at registration, invalid credentials at login) must produce a response that clearly communicates failure to the relevant flow (page re-render for registration, JSON error payload for login) without crashing the request or leaking internal error detail beyond what's needed for the user-facing message.

### FR-05: Search Processing
The search endpoint must accept a query parameter and use it to filter results against both the username and email fields, returning matching rows rendered as HTML.

### FR-06: Persistence
All user data written via registration must persist in the SQLite database across requests and across application restarts, with no in-memory-only storage path for user records.

---

## 5. Complete Visual Design Specification

### 5.1 Global Design System

**Typography family**: `Segoe UI, system-ui, -apple-system, sans-serif`

**Typography scale:**

| Element | Size | Weight |
|---|---|---|
| Main titles | 2rem | 800 |
| Section titles | 1.4rem | 700 |
| Form titles | 1.7rem | 700 |
| Card titles | 0.95rem | 700 |
| Body text | 0.9rem | 400 |
| Labels | 0.82rem | 600 |
| Buttons | 1rem | 600 |

**Primary color palette:**

| Color | Hex |
|---|---|
| Deep indigo (primary) | `#1a237e` |
| Indigo (accent/interactive) | `#3949ab` |
| Indigo (mid-gradient) | `#283593` |
| Near-black (dark accent) | `#0f172a` |
| Off-white (page/body background) | `#eef1f8` |
| White (surfaces) | `#ffffff` |

**Text colors:**

| Use | Hex |
|---|---|
| Primary text | `#1e293b` |
| Secondary text | `#475569` |
| Tertiary/muted text | `#64748b` |
| Light text on dark surfaces | `#c5cae9` |
| Heading/brand text | `#1a237e` |

**Border radius:**

| Element | Radius |
|---|---|
| Inputs | 8px |
| Buttons | 8px |
| Cards | 10–12px |
| Status tags | 6px |

**Shadows:**

| Use | Value |
|---|---|
| Header | `0 2px 10px rgba(26,35,126,0.08)` |
| Card hover | `0 4px 16px rgba(26,35,126,0.10)` |
| Focus glow | `0 0 0 3px rgba(57,73,171,0.12)` |

### 5.2 Shared Header

- Fixed position, 70px height, white background, bottom border, header shadow (see above).
- App title anchored left.
- Three organizational logos anchored right, each 54×54px.
- Present, in this same visual form, on every page (login, signup, dashboard).

### 5.3 Login Page

Two-column, 50/50 split-screen layout.

**Left panel:**
- Deep blue gradient background: `#0d1b5e → #1a237e → #283593`.
- Contains a small badge/label, a welcome heading, a short description, and a bullet list.
- Decorative overlay: semi-transparent white circles at roughly 7% opacity, layered over the gradient.

**Right panel:**
- White background.
- Centered form, max width 400px, containing (top to bottom): form title, subtitle, username field, password field, an error-message area, a full-width login button, and a link to the signup page.
- **Login button**: `#1a237e` background, white text, full width.
- **Input styling**: `#f8f9ff` background, `1.5px solid #c5cae9` border by default; on focus, border color changes to `#3949ab` accompanied by the focus-glow shadow.
- **Error messages**: light red background, red border, dark red text — rendered inline in the error-message area, not as a browser alert.

### 5.4 Signup Page

Structurally identical to the login page: same two-column split, same gradient, same decorative circles on the left panel, same input/button/error styling on the right.

- Form fields (top to bottom): username, email, password, confirm password.
- **Password mismatch**: detected client-side; shown as red text directly beneath the confirm-password field, without a page reload and without blocking further typing.

### 5.5 Dashboard

- Page/body background: `#eef1f8`.
- **Hero banner** directly beneath the shared header:
  - Gradient background `#1a237e → #3949ab`.
  - Left section: page title and subtitle.
  - Right section: the logged-in username plus a semi-transparent white logout button.
- **Content area**: max width 1100px, centered.
- **Mission card**: white card containing a section title and descriptive body text.
- **"Vulnerabilities to Discover" section**: uppercase, small, bold section header, followed by a two-column grid of 8 vulnerability cards.
  - Each card: white background, rounded corners, light border, hover shadow (card-hover shadow value above).
  - Each card carries a colored pill/tag plus a short description.
  - **Tag colors**:

    | Category | Color |
    |---|---|
    | SQLi | Yellow |
    | XSS | Red |
    | Session | Purple |
    | Brute (rate limiting) | Orange |
    | Crypto (password storage) | Green |
    | Exposed (database) | Blue |
    | CSRF | Pink |

- **Process steps section**: three cards ("Find", "Exploit", "Mitigate"), each with `#1a237e` background, a circular numbered badge, and white text.

### 5.6 Responsive Behavior

- **Desktop**: split-screen layout on auth pages as described above.
- **Mobile**: auth pages stack vertically (decorative panel above or below the form, not side-by-side); dashboard's vulnerability grid collapses to a single column; process-step cards stack vertically; header logos shrink to fit the reduced width.

---

## 6. Form Specifications

### 6.1 Registration Form
- 4 inputs: username, email, password, confirm password.
- Client-side check compares password and confirm-password **before** allowing submission; on mismatch, submission is blocked and an inline message is shown.
- On a valid match, the form submits as a standard (non-AJAX) POST.

### 6.2 Login Form
- 2 inputs: username, password.
- Submitted via asynchronous `fetch()`, not a standard form POST.
- The success/failure JSON response is processed by client-side JavaScript, which updates the DOM (error message) or navigates (redirect) accordingly — the page never performs a full reload as part of this exchange.

---

## 7. Validation Rules

- **Registration**: username, email, and password are all required (non-empty). Username uniqueness is enforced at the database level (a duplicate insert must fail rather than silently overwrite or duplicate).
- **Login**: username and password are both required (non-empty).
- **Search**: the query parameter is required; a request without it does not attempt a match.

---

## 8. Session State Model

**Stored values**: `user_id`, `username`, `email`.

**Lifecycle:**
- **Creation**: all three values are written to the session together, immediately after successful authentication in the login flow — never partially populated.
- **Usage**: protected routes read from this session state to establish identity and authorization; the dashboard reads `username` specifically to render user context.
- **Destruction**: logout clears the session in full — all three values are removed together, not individually — such that no subset of authenticated capability survives a logout.

---

## 9. Data Lifecycle Rules

- A user record is created exactly once, at registration.
- There is **no modification workflow**: nothing in this foundation allows an existing user row to be updated.
- There is **no deletion workflow**: nothing in this foundation allows a user row to be removed.
- There is **no recovery workflow**: there is no password-reset or account-recovery mechanism; a lost password has no self-service remedy at this stage.

---

## 10. Success Paths

**SP-01 — Registration**: valid, unique registration data is submitted → user row is created → response redirects to the login page.

**SP-02 — Login**: valid credentials are submitted → session is established with `user_id`/`username`/`email` → client receives a success response and redirects to the dashboard.

**SP-03 — Dashboard**: an authenticated request reaches the dashboard route → session check passes → template is loaded and the username is substituted → the personalized dashboard HTML is returned.

**SP-04 — Logout**: an authenticated user initiates logout → session is fully cleared → client is redirected to the login page.

---

## 11. Alternate Paths

**AP-01 — Duplicate username at registration**: registration is submitted with a username that already exists → the database-level uniqueness constraint rejects the insert → the user is shown a failure response rather than being redirected to login.

**AP-02 — Invalid credentials at login**: login is submitted with a username/password combination that does not match a stored user → no session is established → a JSON error response is returned and rendered inline on the login form.

**AP-03 — Unauthorized dashboard access**: a request reaches the dashboard route without the expected session state → the request is redirected to the login page instead of receiving dashboard content.

**AP-04 — Empty search**: a search request is made with an empty or missing query parameter → no matching rows are returned (rather than, e.g., every row).

---

## 12. Edge Cases

**EC-01**: Registration attempted with a username that already exists in the database.
**EC-02**: Registration form submitted with one or more required fields empty.
**EC-03**: Login form submitted with one or more required fields empty.
**EC-04**: A request for a protected route arrives with no session present at all (e.g., a fresh browser with no cookie).
**EC-05**: A request arrives with a session that is present but malformed/corrupted (does not contain the expected keys).
**EC-06**: A requested template file is missing from disk at request time.
**EC-07**: The SQLite database file is missing at request time (not just at startup).
**EC-08**: The application is restarted while existing user data is present in the database — data must survive the restart and remain queryable afterward.

---

## 13. Business Rules

1. Authenticated status is derived **entirely** from session presence — there is no secondary authorization signal (e.g., a database re-check) on every protected request.
2. The dashboard's personalized content is produced by **runtime string substitution** into a template read fresh from disk, not by a pre-rendered or cached page.
3. User records are **immutable** after creation within this foundation — no update path exists.
4. Login and registration deliberately use **different response formats**: login responds with JSON (consumed by client-side `fetch` logic), registration responds with a redirect/page render (consumed by the browser's native form-submission navigation).
5. Template edits are **visible without an application restart**, because templates are read from disk per-request rather than cached at startup.
6. **Database-level constraint enforcement** (uniqueness on username) is the primary and only mechanism preventing duplicate accounts — there is no separate pre-check query relied upon as the source of truth.

---

## 14. Rebuild Requirements

A compatible reimplementation must reproduce:

- Startup-time database initialization that creates the schema if absent and never destroys existing data.
- Per-request template loading (no template caching).
- Runtime string substitution for injecting the username into the dashboard.
- Session-presence-only authorization on protected routes.
- The exact registration flow: client-side password-confirmation check → standard form POST → server-side create → redirect to login.
- The exact login flow: client-side `fetch()` submission → JSON response → client-driven redirect on success / inline error rendering on failure.
- The exact logout flow: full session clear → redirect to login.
- The complete visual design system specified in §5, including the exact color values, typography scale, border radii, shadows, and page layouts (login/signup split-screen, dashboard hero + card grid).
- The 8-card vulnerability grid on the dashboard with the specified tag colors.
- Responsive collapse behavior for mobile viewports.
- All validation and edge-case behavior described in §7 and §12.

---

## 15. Acceptance Criteria

**AC-01 — Registration**: Given valid, unique signup data, when the form is submitted, then a new user row exists in the database and the browser is redirected to the login page.

**AC-02 — Login**: Given valid credentials, when the login form is submitted, then a session is established with `user_id`, `username`, and `email`, and the client is redirected to the dashboard.

**AC-03 — Dashboard**: Given an authenticated session, when the dashboard route is requested, then the returned HTML contains the current session's username substituted into the template.

**AC-04 — Logout**: Given an authenticated session, when logout is initiated, then the session is fully cleared and a subsequent dashboard request redirects to login.

**AC-05 — Search**: Given a query parameter matching an existing username or email, when `/search` is requested, then the matching row(s) appear in the HTML response.

**AC-06 — Persistence**: Given a user created before an application restart, when the application restarts and the user attempts to log in again, then authentication succeeds using the same stored credentials.

---

## 16. Test Cases

| ID | Scenario | Steps | Expected Result |
|---|---|---|---|
| TC-01 | Successful registration | Submit signup with valid, unique data | User created; redirected to `/login` |
| TC-02 | Duplicate username registration | Submit signup with an existing username | Registration fails; no redirect to login |
| TC-03 | Registration with missing field | Submit signup with one required field empty | Request rejected / not persisted |
| TC-04 | Password mismatch on signup | Enter differing password and confirm-password values | Inline red message shown; form does not submit |
| TC-05 | Successful login | Submit login with valid credentials | JSON success response; session established; client redirects to `/welcome` |
| TC-06 | Failed login — wrong password | Submit login with an existing username and wrong password | JSON error response; error shown inline; no session created |
| TC-07 | Failed login — missing field | Submit login with username or password empty | Request rejected without establishing a session |
| TC-08 | Dashboard access while authenticated | Log in, then request `/welcome` | Dashboard HTML returned with correct username substituted |
| TC-09 | Dashboard access while unauthenticated | Request `/welcome` with no prior login | Redirected to `/login` |
| TC-10 | Logout clears session | Log in, then log out, then request `/welcome` | Redirected to `/login` (session no longer valid) |
| TC-11 | Search with matching query | Request `/search?q=<existing username or email>` | Matching row(s) rendered in response |
| TC-12 | Search with no match | Request `/search?q=<nonexistent string>` | No rows rendered |
| TC-13 | Search with empty query | Request `/search` with no `q` parameter | No rows rendered / no match attempted |
| TC-14 | Template hot-edit | Edit a template file, then re-request the corresponding page without restarting the app | Updated content appears immediately |
| TC-15 | Restart persistence | Register a user, restart the application, log in again with the same credentials | Login succeeds; user data survived the restart |

---

## 17. Documentation Gaps

1. **PRD Appendix B / TDD §6.2 quick-start commands assume a `backend/` subproject** (`cd backend && uv sync`, `python app/main.py`), but neither document specifies whether the top-level project (this addendum's actual build target) uses that same two-tier structure or a single root-level `pyproject.toml`. The setup commands should not be treated as authoritative about final directory layout.

2. **PRD FR-3 and TDD's endpoint registry both name the protected route `/welcome`**, while the PRD's own Epic/User-Story language and TDD's Vulnerability Injection Flow both refer to it informally as "the dashboard." Neither document states whether "dashboard" is ever a literal route path — it is a UI/content concept only, and this addendum treats `/welcome` as the sole protected route.

3. **Neither PRD nor TDD documents the login response's exact JSON shape** (field names for success payload vs. error payload). This addendum's flows (§3.2, §6.2) describe the *behavior* the client depends on (a distinguishable success/failure outcome consumed by `fetch()` logic) without inventing a field-level contract that isn't sourced from either document.

4. **The TDD's two "Project Structure" listings (§6.5 and §11.2) are not identical** — §6.5 includes `README.md`, `CLAUDE.md`, and `docs/EXPLOITS.md` at the root and a `requirements.txt` alongside `pyproject.toml` in `backend/`; §11.2 omits all of these. This addendum does not assume the existence of `EXPLOITS.md`, `CLAUDE.md`, or `requirements.txt` since neither is otherwise referenced by any functional requirement in either document.
