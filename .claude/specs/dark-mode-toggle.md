# Software Specification Document (Implementation Addendum)

## Vulnerable Web Application — Dark Mode Toggle

**Version:** 1.0.0
**Companion Documents:** `docs/PRD.md`, `docs/TDD.md`, `.claude/specs/app-foundation.md`

---

## 1. Overview / Purpose

This document specifies a light/dark theme toggle for the login, signup, and dashboard pages. The toggle is a purely presentational, additive feature: it lets a user switch between a light and a dark color scheme, persists that choice in the browser's `localStorage`, and restores it on subsequent visits — falling back to the operating system's `prefers-color-scheme` when no preference has been saved. It introduces no new backend routes, no new server-side state, and no new dependencies; it is implemented entirely with CSS custom properties, a `data-theme` attribute on `<html>`, and a small inline script per page.

---

## 2. Scope & Non-Goals

### In Scope
- A visible, keyboard-accessible theme toggle control present on the login, signup, and dashboard pages.
- A dark color palette expressed as CSS custom-property overrides, applied via `[data-theme="dark"]` on `<html>`.
- Client-side persistence of the chosen theme in `localStorage` under the key `"theme"`.
- Pre-render theme restoration (to prevent a flash of the wrong theme) and `prefers-color-scheme` fallback when no stored value exists.

### Non-Goals / Explicitly Out of Scope
- No backend route, session field, or database column is added to store theme preference server-side.
- No changes to authentication, routing, or business logic in any Python file.
- No build step, bundler, or frontend framework is introduced.

### Vulnerability Status — All 8 Remain Unfixed and In Their Original State

This feature is purely a visual/UX addition layered on top of the existing foundation. None of the 8 intentional vulnerabilities are in scope for remediation, and this feature must not incidentally alter their behavior:

| # | Vulnerability | Status |
|---|---|---|
| 1 | SQL Injection (`auth_service.py`) | Unaffected — no auth/query logic touched. Remains unfixed. |
| 2 | Stored XSS (`{{username}}` in `/welcome`) | Unaffected — the unescaped substitution in `dashboard.html` must continue to render exactly as before, alongside the new toggle markup. Remains unfixed. |
| 3 | Reflected XSS (`/search` `q` param) | Unaffected — `/search` is not touched by this feature. Remains unfixed. |
| 4 | Session Hijacking (hardcoded `SECRET_KEY`) | Unaffected — no session or middleware code is touched. Remains unfixed. |
| 5 | Weak Password Storage (unsalted MD5) | Unaffected — no hashing code is touched. Remains unfixed. |
| 6 | Exposed Database (`GET /download/db`) | Unaffected — no route protection is added anywhere, including this endpoint. Remains unfixed. |
| 7 | No Rate Limiting | Unaffected — no throttling middleware is introduced by this feature. Remains unfixed. |
| 8 | CSRF | Unaffected — no CSRF token or validation is added to any form, including any new toggle-related control. Remains unfixed. |

---

## 3. Affected Files

- `frontend/static/css/styles.css`
- `frontend/templates/login.html`
- `frontend/templates/signup.html`
- `frontend/templates/dashboard.html`

No other file in the repository is affected. No backend file (`backend/app/**`) is touched.

---

## 4. Functional Requirements

### FR-01: Toggle Control Present on All Three Pages
A theme toggle control must be rendered in the shared header (`.app-header`) on the login, signup, and dashboard pages, in the same visual position across all three.

### FR-02: Theme Application via `data-theme` Attribute
The active theme must be reflected as `data-theme="light"` or `data-theme="dark"` on the `<html>` element. All themed styling must be expressed as CSS custom-property overrides scoped to `[data-theme="dark"]`, layered on top of the existing `:root` tokens in `styles.css` — no existing selector, layout rule, or color value in `:root` may be deleted or renamed.

### FR-03: Persistence in localStorage
On toggle activation, the resulting theme value (`"light"` or `"dark"`) must be written to `localStorage` under the key `"theme"`.

### FR-04: Pre-Render Restoration (No Flash of Wrong Theme)
On each page load, a small inline script placed before the page's visible content is rendered must read `localStorage.getItem("theme")` and apply the corresponding `data-theme` attribute to `<html>` before the browser paints the page, so no flash of the incorrect theme is visible.

### FR-05: System Preference Fallback
If no value is present under the `"theme"` key in `localStorage`, the initial theme must be derived from the `prefers-color-scheme` media feature (`dark` → dark theme, otherwise → light theme), without writing that derived value back to `localStorage` until the user explicitly toggles.

### FR-06: Keyboard Accessibility
The toggle control must be a native, focusable, keyboard-operable element (e.g., a `<button>`), reachable via `Tab` and activatable via `Enter`/`Space`, consistent with native button semantics — no custom non-interactive element (e.g., a `<div>` with a click handler) may be used.

### FR-07: Dynamic `aria-label`
The toggle's `aria-label` must describe the action the control performs next, not the current state — e.g., `aria-label="Switch to dark mode"` while light is active, `aria-label="Switch to light mode"` while dark is active — and must update immediately whenever the theme changes.

### FR-08: No Regression to Existing Markup or Behavior
Existing form fields, IDs, `fetch()` logic, client-side validation scripts, and the dashboard's `{{username}}` substitution point must remain byte-for-byte unchanged in structure and behavior; only additive markup (the toggle control and its inline scripts) and additive CSS may be introduced.

---

## 5. Non-Functional Requirements

### NFR-01: No Framework, No Build Step
The toggle must be implemented with vanilla JavaScript embedded in each template's existing `<script>` block (or a new inline block following the same pattern already used in `login.html`/`signup.html`), and plain CSS custom properties — no external library, no bundler, no new `<script src>` dependency.

### NFR-02: Consistent Visual Language
Dark-theme color values must preserve the existing typography scale, spacing, border-radius, and shadow tokens defined in `styles.css` §"Design tokens" — only color-related custom properties are overridden per theme; radii, shadows' blur/spread, and font sizes are shared across both themes (shadow color/opacity may be adjusted for legibility on dark surfaces).

### NFR-03: No Added Network Requests
Theme restoration and persistence must not introduce any HTTP request (no server round-trip to read or write the preference).

### NFR-04: No Layout Shift From Toggle Presence
Adding the toggle control to `.app-header` must not change the fixed 70px header height or push/reflow the three existing header logos.

### NFR-05: Consistent Behavior Across Pages
The toggle's visual state, persisted value, and restoration logic must behave identically on login, signup, and dashboard — a theme chosen on one page must be honored on navigation to either of the other two.

---

## 6. Success Paths

**SP-01 — First visit, no system preference for dark**: User loads `/login` with empty `localStorage` and a light OS preference → page renders in light theme → no `"theme"` key is written until the user toggles.

**SP-02 — First visit, system prefers dark**: User loads `/login` with empty `localStorage` and a dark OS preference → page renders in dark theme via the `prefers-color-scheme` fallback → no `"theme"` key is written until the user toggles.

**SP-03 — Manual toggle**: User clicks/activates the toggle on any of the three pages → theme flips immediately, `data-theme` updates, `aria-label` updates, and `localStorage["theme"]` is written with the new value.

**SP-04 — Returning visit with saved preference**: User has previously toggled to dark and returns to any of the three pages → the page restores dark theme before first paint, with no flash of light theme.

**SP-05 — Cross-page consistency**: User sets dark theme on the login page, then navigates to signup or (after authenticating) to the dashboard → the same dark theme is applied on load, sourced from the same `localStorage` key.

---

## 7. Edge Cases

**EC-01**: `localStorage` is unavailable or throws (e.g., disabled by browser settings/private mode restrictions) — the page must still render using the `prefers-color-scheme` fallback rather than failing to load.

**EC-02**: `localStorage["theme"]` contains an unexpected/corrupted value (neither `"light"` nor `"dark"`) — the page must fall back to `prefers-color-scheme` rather than applying an invalid `data-theme` value.

**EC-03**: User has no OS-level color-scheme preference exposed (`prefers-color-scheme: no-preference` or unsupported) — the page must default to the light theme.

**EC-04**: User toggles theme rapidly multiple times in succession — the final `localStorage["theme"]` value and the final `data-theme` attribute must both reflect the last toggle action, with no lost or out-of-order writes.

**EC-05**: JavaScript is disabled entirely — the page must still render using whatever theme its static, non-scripted default is (light), since no dynamic restoration or toggle can run without JavaScript.

---

## 8. Acceptance Criteria

**AC-01 — Toggle present and functional on all pages**: Given any of `/login`, `/signup`, or the dashboard, when the page is loaded, then a keyboard-focusable theme toggle is present in the header and activating it switches `data-theme` on `<html>` between `"light"` and `"dark"`.

**AC-02 — Persistence**: Given a user activates the toggle, when the page is reloaded or a different one of the three pages is loaded, then the previously chosen theme is restored without requiring the user to toggle again.

**AC-03 — No flash of wrong theme**: Given a saved `"theme"` value in `localStorage`, when any of the three pages loads, then the correct theme is applied before the page's first paint (verified by absence of a visible flash from light to dark or vice versa).

**AC-04 — System preference fallback**: Given no `"theme"` key exists in `localStorage`, when a page loads, then the applied theme matches the browser's `prefers-color-scheme` value.

**AC-05 — Accessible label reflects next action**: Given the current theme is light, when the toggle's `aria-label` is inspected, then it reads as an instruction to switch to dark mode (and vice versa when dark is active).

**AC-06 — Existing vulnerabilities untouched**: Given the dashboard is rendered for an authenticated user, when the response HTML is inspected, then the `{{username}}` placeholder is still substituted via unescaped string replacement (i.e., a username containing a `<script>` payload still renders as live, unescaped markup in the response).

---

## 9. Test Cases

| ID | Scenario | Precondition | Expected Result |
|---|---|---|---|
| TC-01 | Toggle switches theme on login page | `/login` loaded, light theme active | Clicking/activating toggle sets `data-theme="dark"` on `<html>` and updates visible colors |
| TC-02 | Toggle switches theme on signup page | `/signup` loaded, light theme active | Clicking/activating toggle sets `data-theme="dark"` on `<html>` and updates visible colors |
| TC-03 | Toggle switches theme on dashboard | Authenticated, dashboard loaded, light theme active | Clicking/activating toggle sets `data-theme="dark"` on `<html>` and updates visible colors |
| TC-04 | Theme persists across reload | Theme toggled to dark on `/login` | Reloading `/login` restores dark theme without a visible flash |
| TC-05 | Theme persists across page navigation | Theme toggled to dark on `/login` | Navigating to `/signup` restores dark theme |
| TC-06 | System preference fallback (dark) | `localStorage` empty, OS/browser set to prefer dark | Page loads in dark theme |
| TC-07 | System preference fallback (light) | `localStorage` empty, OS/browser set to prefer light | Page loads in light theme |
| TC-08 | Keyboard operability | Toggle control present, no mouse used | Tabbing reaches the toggle; `Enter`/`Space` activates it and switches the theme |
| TC-09 | aria-label reflects next action | Light theme active | Toggle's `aria-label` indicates switching to dark; after activating, indicates switching to light |
| TC-10 | Corrupted localStorage value | `localStorage["theme"]` manually set to an invalid string (e.g., `"blue"`) | Page falls back to `prefers-color-scheme` rather than erroring or applying an invalid attribute |
| TC-11 | Header layout unaffected | Toggle added to header on any page | Header height remains 70px; existing three logos remain visible and unshifted |
| TC-12 | Existing login flow unaffected | Toggle present on `/login` | Submitting valid credentials via the existing `fetch()` flow still redirects to the dashboard as before |
| TC-13 | Existing signup flow unaffected | Toggle present on `/signup` | Submitting valid signup data still performs a standard POST and redirects to `/login` as before |
| TC-14 | Existing stored XSS still exploitable | Toggle present on dashboard, user registered with a username containing `<script>alert(1)</script>` | Dashboard response still contains the payload unescaped in place of `{{username}}`, confirming VULN-2 is intact |

---

## 10. Verification Steps

1. From the project root, install dependencies and start the application:
   ```bash
   cd backend && uv sync
   uv run backend/app/main.py
   ```
2. Open `http://localhost:3001/login` — confirm the toggle is visible in the header and the initial theme matches the browser's `prefers-color-scheme`.
3. Activate the toggle — confirm the page switches theme immediately and `localStorage["theme"]` (via browser dev tools) reflects the new value.
4. Reload `http://localhost:3001/login` — confirm the previously chosen theme is restored with no visible flash.
5. Navigate to `http://localhost:3001/signup` — confirm the same theme persists.
6. Log in and load the dashboard (`http://localhost:3001/welcome`) — confirm the theme persists there as well, and confirm the toggle is present and functional in the dashboard header.
7. Using keyboard only (`Tab` then `Enter`/`Space`), confirm the toggle can be reached and activated without a mouse, and confirm its `aria-label` updates to describe the next action.
8. Register a user with a username of `<script>alert(1)</script>` and confirm on the dashboard that VULN-2 (stored XSS) is still present and unaffected by this feature.
