# Implementation Plan

## Vulnerable Web Application — Dark Mode Toggle

**Version:** 1.0.0
**Implements:** `.claude/specs/dark-mode-toggle.md`
**Companion Documents:** `docs/PRD.md`, `docs/TDD.md`, `.claude/specs/app-foundation.md`

---

## 0. Plan Overview

This plan implements the dark mode toggle described in `.claude/specs/dark-mode-toggle.md` in four phases:

1. **Phase 1** — CSS foundation: dark-theme custom-property overrides and toggle control styling in `frontend/static/css/styles.css`.
2. **Phase 2** — Shared toggle markup + inline pre-paint init script + click handler, applied identically to `frontend/templates/login.html` and `frontend/templates/signup.html`.
3. **Phase 3** — Same toggle markup/script applied to `frontend/templates/dashboard.html`, with explicit verification that the `{{username}}` substitution point (VULN-2) is untouched.
4. **Phase 4** — Manual verification against the spec's Test Cases (§9) and Verification Steps (§10).

This is an **additive-only** change. No phase removes, escapes, sanitizes, parameterizes, rate-limits, or CSRF-protects anything. No Python file under `backend/app/**` is touched in any phase.

---

## Phase 1 — CSS Foundation

**File:** `frontend/static/css/styles.css`

### 1.1 Add dark-theme custom-property overrides

Insert a new block immediately after the existing `:root { ... }` block (i.e., right after line 29, before the `/* Reset / base */` comment). This scopes all dark-theme color values to `[data-theme="dark"]` on `<html>`, per FR-02. Only color-related tokens are overridden — radii, shadows' shape, and font sizes are inherited unchanged from `:root`, per NFR-02.

**Before:**
```css
:root {
    --color-primary: #1a237e;
    --color-accent: #3949ab;
    --color-mid: #283593;
    --color-dark: #0f172a;
    --color-bg: #eef1f8;
    --color-white: #ffffff;

    --text-primary: #1e293b;
    --text-secondary: #475569;
    --text-muted: #64748b;
    --text-on-dark: #c5cae9;
    --text-heading: #1a237e;

    --radius-input: 8px;
    --radius-button: 8px;
    --radius-card: 12px;
    --radius-tag: 6px;

    --shadow-header: 0 2px 10px rgba(26, 35, 126, 0.08);
    --shadow-card-hover: 0 4px 16px rgba(26, 35, 126, 0.10);
    --shadow-focus: 0 0 0 3px rgba(57, 73, 171, 0.12);

    --font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
}

/* ==========================================================================
   Reset / base
   ========================================================================== */
```

**After (new block inserted between them):**
```css
:root {
    --color-primary: #1a237e;
    --color-accent: #3949ab;
    --color-mid: #283593;
    --color-dark: #0f172a;
    --color-bg: #eef1f8;
    --color-white: #ffffff;

    --text-primary: #1e293b;
    --text-secondary: #475569;
    --text-muted: #64748b;
    --text-on-dark: #c5cae9;
    --text-heading: #1a237e;

    --radius-input: 8px;
    --radius-button: 8px;
    --radius-card: 12px;
    --radius-tag: 6px;

    --shadow-header: 0 2px 10px rgba(26, 35, 126, 0.08);
    --shadow-card-hover: 0 4px 16px rgba(26, 35, 126, 0.10);
    --shadow-focus: 0 0 0 3px rgba(57, 73, 171, 0.12);

    --font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
}

/* ==========================================================================
   Dark theme overrides
   ========================================================================== */

[data-theme="dark"] {
    --color-primary: #3949ab;
    --color-accent: #5c6bc0;
    --color-mid: #283593;
    --color-dark: #0f172a;
    --color-bg: #0f1117;
    --color-white: #1a1d29;

    --text-primary: #e2e8f0;
    --text-secondary: #a8b3c5;
    --text-muted: #7c8aa3;
    --text-on-dark: #c5cae9;
    --text-heading: #c5cae9;

    --shadow-header: 0 2px 10px rgba(0, 0, 0, 0.35);
    --shadow-card-hover: 0 4px 16px rgba(0, 0, 0, 0.45);
    --shadow-focus: 0 0 0 3px rgba(92, 107, 192, 0.25);
}

/* ==========================================================================
   Reset / base
   ========================================================================== */
```

*Note:* `--color-white` is repurposed as "surface color" under dark theme (a dark elevated surface, not literal white) so that existing rules like `.mission-card { background: var(--color-white); }` and `.vuln-card { background: var(--color-white); }` automatically become dark surfaces with zero changes to those selectors — this is what makes the override purely additive at the token layer.

Also add a `body` transition and border-color adjustment so the theme swap is smooth and card borders remain visible on dark surfaces, appended after the existing `body { ... }` rule (not modifying its existing declarations) and after `.vuln-card`'s existing border declaration is left as-is (it already uses a hardcoded `#e2e6f2`, which is acceptably subtle on dark backgrounds since `--color-white` becomes dark — a further override is optional and not required by any FR/NFR, so it is deferred unless verification in Phase 4 shows a legibility problem).

**Edit — add color-scheme + transition to `body`:**

Before:
```css
body {
    font-family: var(--font-family);
    color: var(--text-primary);
    font-size: 0.9rem;
    font-weight: 400;
    line-height: 1.5;
}
```

After:
```css
body {
    font-family: var(--font-family);
    color: var(--text-primary);
    font-size: 0.9rem;
    font-weight: 400;
    line-height: 1.5;
    background: var(--color-bg);
    transition: background-color 0.15s ease, color 0.15s ease;
}
```

*Rationale:* the existing `body` rule has no explicit `background`, so auth pages currently rely on `.auth-right`'s white background and `.dashboard-body`'s `--color-bg`. Setting `background: var(--color-bg)` on the base `body` rule ensures the page background (including any margin outside `.auth-split`/`.dashboard-body`) switches themes too, without altering any existing selector's own background declarations.

### 1.2 Add toggle control styling

Append a new section at the end of the file (after the existing `@media (max-width: 900px) { ... }` block), styling the toggle button referenced in Phase 2/3. Placed in `.header-logos`'s flex row via markup (Phase 2), so it inherits `.header-logos`'s `display: flex; align-items: center; gap: 16px;` — no changes needed to `.header-logos` itself, satisfying NFR-04 (no layout shift to existing logos, since the toggle is simply one more flex item in the same row using its own fixed size).

**Append:**
```css

/* ==========================================================================
   Theme toggle
   ========================================================================== */

.theme-toggle {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 38px;
    height: 38px;
    border-radius: 50%;
    border: 1.5px solid #c5cae9;
    background: #f8f9ff;
    color: var(--text-heading);
    font-size: 1.1rem;
    line-height: 1;
    cursor: pointer;
    transition: background-color 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}

.theme-toggle:hover {
    background: #eef1f8;
}

.theme-toggle:focus-visible {
    outline: none;
    box-shadow: var(--shadow-focus);
    border-color: var(--color-accent);
}

[data-theme="dark"] .theme-toggle {
    background: #1a1d29;
    border-color: #3b4252;
    color: var(--text-on-dark);
}

[data-theme="dark"] .theme-toggle:hover {
    background: #232838;
}
```

The icon glyph itself (e.g., ☀ / ☾) is set as the button's text content in markup (Phase 2), not via CSS `content`, so it can be updated in the same script that flips `aria-label`.

### 1.3 Verification for Phase 1

- Open `styles.css` and confirm no existing selector, property, or value under `:root` or elsewhere was deleted or renamed — only new blocks were added and one new declaration (`background`, `transition`) was added to the existing `body` rule.
- Visually inspect (once Phase 2/3 markup exists) that `[data-theme="dark"]` on `<html>` recolors surfaces without changing any spacing, radius, or font size.

---

## Phase 2 — Toggle Markup + Script on Login and Signup Pages

**Files:** `frontend/templates/login.html`, `frontend/templates/signup.html`

Both pages get an identical change, applied independently to each file (templates are read from disk per-request with no shared include mechanism in this codebase, per the app-foundation spec §2, so the same markup/script block is duplicated in each file rather than factored into a shared partial — consistent with NFR-01's "no build step").

### 2.1 Add pre-paint init script in `<head>`

Insert a `<script>` immediately before `</head>`, after the existing `<link rel="stylesheet">` tag. This runs before body content paints, fulfilling FR-04 (no flash of wrong theme) and FR-05 (system preference fallback) and handling EC-01/EC-02 (missing/invalid localStorage) via try/catch and value validation.

**Before (`login.html`, lines 1–8):**
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Security Vulnerability Lab</title>
    <link rel="stylesheet" href="/static/css/styles.css">
</head>
```

**After:**
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Security Vulnerability Lab</title>
    <link rel="stylesheet" href="/static/css/styles.css">
    <script>
        (function () {
            var storedTheme = null;
            try {
                storedTheme = localStorage.getItem('theme');
            } catch (err) {
                storedTheme = null;
            }
            var theme = (storedTheme === 'light' || storedTheme === 'dark')
                ? storedTheme
                : (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
            document.documentElement.setAttribute('data-theme', theme);
        })();
    </script>
</head>
```

The identical block (only the surrounding `<title>` differs per file, which is untouched) is inserted into `signup.html` at the same position (after its `<link rel="stylesheet">`, before `</head>`).

This script:
- Wraps `localStorage.getItem` in try/catch → satisfies EC-01 (localStorage unavailable/throws).
- Validates the stored value is exactly `"light"` or `"dark"` before trusting it → satisfies EC-02 (corrupted value falls through to the media-query fallback).
- Uses `window.matchMedia('(prefers-color-scheme: dark)').matches` → satisfies FR-05; when unsupported (`window.matchMedia` undefined) or no preference, the `matches` check is falsy and the theme defaults to `'light'` → satisfies EC-03.
- Runs synchronously in `<head>` before body render → satisfies FR-04. If JavaScript is disabled entirely, this script simply doesn't run and `<html>` has no `data-theme` attribute, so the page renders using the plain `:root` (light) values as its static default → satisfies EC-05.
- Does **not** write to `localStorage` in this script — only reads — satisfying FR-05's "without writing that derived value back... until the user explicitly toggles."

### 2.2 Add the toggle button to the header

Insert a `<button>` inside `.header-logos`, after the last `<img>`, so it participates in the same flex row (FR-01, NFR-04). Its initial visible glyph/label is a static default (light-mode-appropriate); the click handler script (2.3) sets the correct glyph/label to match the theme resolved in 2.1 once the DOM is parsed.

**Before (`login.html`, lines 10–17):**
```html
    <header class="app-header">
        <div class="header-title">Security Vulnerability Lab</div>
        <div class="header-logos">
            <img src="/static/images/PUCIT_Logo.png" alt="PUCIT logo">
            <img src="/static/images/blue-logo-scl2.png" alt="Organization logo">
            <img src="/static/images/excaliat-logo.png" alt="Excaliat logo">
        </div>
    </header>
```

**After:**
```html
    <header class="app-header">
        <div class="header-title">Security Vulnerability Lab</div>
        <div class="header-logos">
            <img src="/static/images/PUCIT_Logo.png" alt="PUCIT logo">
            <img src="/static/images/blue-logo-scl2.png" alt="Organization logo">
            <img src="/static/images/excaliat-logo.png" alt="Excaliat logo">
            <button type="button" id="theme-toggle" class="theme-toggle" aria-label="Switch to dark mode">&#9788;</button>
        </div>
    </header>
```

`&#9788;` is `☀` (sun, light-mode default glyph). Using a native `<button type="button">` satisfies FR-06 (keyboard-focusable, `Enter`/`Space`-activatable by default HTML semantics, no custom click-only element).

### 2.3 Add the click handler + state-sync script before `</body>`

Insert a new `<script>` block just before the existing `<script>` (login) / at the end of the existing `<script>` (signup) — placed so it runs after the DOM (including the button) is parsed. For `login.html`, this is added as a **separate** `<script>` block preceding the existing login-form `<script>`, to keep the login-submit logic untouched per FR-08. For `signup.html`, likewise added as a separate block preceding the existing signup-form `<script>`.

**`login.html` — before (lines 62–89, existing script untouched):**
```html
    <script>
        document.getElementById('login-form').addEventListener('submit', async function (e) {
            ...
        });
    </script>
</body>
</html>
```

**`login.html` — after:**
```html
    <script>
        (function () {
            var toggleBtn = document.getElementById('theme-toggle');

            function syncToggleUI(theme) {
                if (theme === 'dark') {
                    toggleBtn.textContent = '☾';
                    toggleBtn.setAttribute('aria-label', 'Switch to light mode');
                } else {
                    toggleBtn.textContent = '☀';
                    toggleBtn.setAttribute('aria-label', 'Switch to dark mode');
                }
            }

            syncToggleUI(document.documentElement.getAttribute('data-theme') || 'light');

            toggleBtn.addEventListener('click', function () {
                var current = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
                var next = current === 'dark' ? 'light' : 'dark';
                document.documentElement.setAttribute('data-theme', next);
                syncToggleUI(next);
                try {
                    localStorage.setItem('theme', next);
                } catch (err) {
                    /* localStorage unavailable; theme still applied for this page view */
                }
            });
        })();
    </script>

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
                const data = await response.json();

                if (data.success) {
                    window.location.href = data.redirect;
                } else {
                    errorEl.textContent = data.error || 'Invalid username or password.';
                    errorEl.style.display = 'block';
                }
            } catch (err) {
                errorEl.textContent = 'Something went wrong. Please try again.';
                errorEl.style.display = 'block';
            }
        });
    </script>
</body>
</html>
```

The same toggle script block is inserted into `signup.html` immediately before its existing `<script>` block (which contains the password-match validation and submit-guard logic), leaving that script's contents completely unmodified.

This script:
- Reads the current `data-theme` (already set correctly by the head script in 2.1) to sync the button's glyph/label on load — this is a UI-sync step, not a re-derivation of theme, so it doesn't duplicate FR-05's fallback logic.
- On click: flips `data-theme`, updates the button's glyph and `aria-label` immediately (FR-07), and persists via `localStorage.setItem('theme', next)` wrapped in try/catch (FR-03, EC-01).
- Because `syncToggleUI` and the `setItem` call always run to completion synchronously inside the click handler before the next click can be processed, rapid repeated clicks resolve in DOM event order — satisfying EC-04 (last click wins, no lost/out-of-order writes).

### 2.4 Verification for Phase 2

- Confirm `login-form`'s existing `id`, `fetch('/login', ...)` call, and JSON-handling logic are unchanged (FR-08, TC-12).
- Confirm `signup-form`'s existing `id`, `action="/signup" method="POST"`, and password-mismatch script are unchanged (FR-08, TC-13).
- Confirm `.header-logos` still contains exactly the three original `<img>` tags plus one new `<button>`, and the header's computed height is still 70px (NFR-04, TC-11).

---

## Phase 3 — Toggle Markup + Script on Dashboard Page

**File:** `frontend/templates/dashboard.html`

Same pattern as Phase 2, applied to the dashboard template, with explicit attention to not disturbing the `{{username}}` substitution point (VULN-2).

### 3.1 Add pre-paint init script in `<head>`

**Before (lines 1–8):**
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - Security Vulnerability Lab</title>
    <link rel="stylesheet" href="/static/css/styles.css">
</head>
```

**After:**
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - Security Vulnerability Lab</title>
    <link rel="stylesheet" href="/static/css/styles.css">
    <script>
        (function () {
            var storedTheme = null;
            try {
                storedTheme = localStorage.getItem('theme');
            } catch (err) {
                storedTheme = null;
            }
            var theme = (storedTheme === 'light' || storedTheme === 'dark')
                ? storedTheme
                : (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
            document.documentElement.setAttribute('data-theme', theme);
        })();
    </script>
</head>
```

Identical script to Phase 2.1 — this is intentional duplication per page (no shared include mechanism exists in this codebase), not a new abstraction.

### 3.2 Add the toggle button to the header

Same header structure as login/signup (`.app-header` / `.header-logos` markup is identical across all three templates already).

**Before (lines 10–17):**
```html
    <header class="app-header">
        <div class="header-title">Security Vulnerability Lab</div>
        <div class="header-logos">
            <img src="/static/images/PUCIT_Logo.png" alt="PUCIT logo">
            <img src="/static/images/blue-logo-scl2.png" alt="Organization logo">
            <img src="/static/images/excaliat-logo.png" alt="Excaliat logo">
        </div>
    </header>
```

**After:**
```html
    <header class="app-header">
        <div class="header-title">Security Vulnerability Lab</div>
        <div class="header-logos">
            <img src="/static/images/PUCIT_Logo.png" alt="PUCIT logo">
            <img src="/static/images/blue-logo-scl2.png" alt="Organization logo">
            <img src="/static/images/excaliat-logo.png" alt="Excaliat logo">
            <button type="button" id="theme-toggle" class="theme-toggle" aria-label="Switch to dark mode">&#9788;</button>
        </div>
    </header>
```

**Important — do not touch the hero banner block below it.** The `{{username}}` substitution (line 25 in the current file: `<span class="user-badge">Logged in as {{username}}</span>`) lives in `.hero-banner`/`.hero-right`, a completely separate section from `.app-header`/`.header-logos`. This plan makes **no edit** to `.hero-banner`, `.hero-right`, `.user-badge`, or the logout link — they are left byte-for-byte identical, preserving VULN-2 exactly as-is (AC-06).

### 3.3 Add the click handler + state-sync script before `</body>`

Dashboard's current `<body>` has no existing `<script>` block (unlike login/signup), so this is a new, standalone addition immediately before `</body>`.

**Before (lines 102–106):**
```html
        </div>
    </main>
</body>
</html>
```

**After:**
```html
        </div>
    </main>

    <script>
        (function () {
            var toggleBtn = document.getElementById('theme-toggle');

            function syncToggleUI(theme) {
                if (theme === 'dark') {
                    toggleBtn.textContent = '☾';
                    toggleBtn.setAttribute('aria-label', 'Switch to light mode');
                } else {
                    toggleBtn.textContent = '☀';
                    toggleBtn.setAttribute('aria-label', 'Switch to dark mode');
                }
            }

            syncToggleUI(document.documentElement.getAttribute('data-theme') || 'light');

            toggleBtn.addEventListener('click', function () {
                var current = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
                var next = current === 'dark' ? 'light' : 'dark';
                document.documentElement.setAttribute('data-theme', next);
                syncToggleUI(next);
                try {
                    localStorage.setItem('theme', next);
                } catch (err) {
                    /* localStorage unavailable; theme still applied for this page view */
                }
            });
        })();
    </script>
</body>
</html>
```

Identical logic to Phase 2.3.

### 3.4 Verification for Phase 3

- Confirm the line `<span class="user-badge">Logged in as {{username}}</span>` is present, unmodified, and still performs raw string substitution server-side (no escaping added) — inspect `backend/app/api/routes/auth.py`'s `/welcome` handler to confirm it is untouched (this plan makes no edit there) (AC-06, TC-14).
- Confirm all 8 `.vuln-card` entries in the "Vulnerabilities to Discover" grid, and the three `.process-card` steps, are unmodified.
- Confirm `.hero-banner`'s gradient, layout, and the logout `<a href="/logout">` are unmodified.

---

## Phase 4 — Manual Verification (per spec §9 Test Cases and §10 Verification Steps)

No further file edits occur in this phase — it is validation only.

### 4.1 Start the application

```bash
cd backend && uv sync
uv run backend/app/main.py
```

### 4.2 Run through spec Verification Steps (§10)

1. Open `http://localhost:3001/login` — confirm the toggle button is visible in the header (four items now in `.header-logos`: three logos + toggle) and the initial theme matches the browser's `prefers-color-scheme`.
2. Click the toggle — confirm the page switches theme immediately; open DevTools → Application → Local Storage and confirm `theme` is set to the new value.
3. Reload `http://localhost:3001/login` — confirm the previously chosen theme is restored with no visible flash.
4. Navigate to `http://localhost:3001/signup` — confirm the same theme persists.
5. Log in and load `http://localhost:3001/welcome` — confirm the theme persists and the toggle is present/functional in the dashboard header.
6. Using keyboard only (`Tab` to reach the toggle, `Enter`/`Space` to activate), confirm operability and that `aria-label` updates (inspect via DevTools Accessibility pane or `document.getElementById('theme-toggle').getAttribute('aria-label')` in console).
7. Register a user with username `<script>alert(1)</script>` and confirm on the dashboard that the payload still executes/renders unescaped — VULN-2 intact.

### 4.3 Execute spec Test Cases (§9) — TC-01 through TC-14

Work through each row of the Test Cases table in `dark-mode-toggle.md` §9, confirming the Expected Result for each. Pay particular attention to:
- **TC-10** (corrupted localStorage): in DevTools console, run `localStorage.setItem('theme', 'blue')`, then reload — confirm fallback to `prefers-color-scheme` rather than an invalid `data-theme="blue"` attribute.
- **TC-12 / TC-13** (existing flows unaffected): confirm login/signup submission behavior is bit-for-bit the same as before this change.
- **TC-14** (VULN-2 intact): confirm explicitly as in §4.2 step 7 above.

### 4.4 Final diff review

Before considering the feature complete, review the full diff against this plan's Phases 1–3 and confirm:
- Only `frontend/static/css/styles.css`, `frontend/templates/login.html`, `frontend/templates/signup.html`, and `frontend/templates/dashboard.html` were modified.
- No file under `backend/app/**` was touched.
- No existing CSS selector, HTML id/class, or script block was deleted or altered beyond the specific additive insertions listed above.
