# Implementation Plan

## Password Strength Meter

**Version:** 1.0.0
**Source Spec:** `.claude/specs/pwd-str-meter.md`
**Companion Documents:** `docs/PRD.md`, `docs/TDD.md`, `.claude/specs/app-foundation.md`, `.claude/specs/dark-mode-toggle.md`, `.claude/specs/csrf-protection-fix.md`

---

## 0. Plan Scope

This plan implements only what `.claude/specs/pwd-str-meter.md` specifies: a real-time, advisory-only strength meter and criteria checklist beneath the Password field on the signup form. It does **not** touch:

- Any file under `backend/app/**` — no server-side password policy, no new `Form(...)` field on `signup_post()`, no change to `auth_service.signup()`, `security.py`, `csrf.py`, or any route.
- `frontend/templates/login.html` — no password-creation flow exists there.
- `frontend/templates/dashboard.html` — no password field exists there.
- The existing `password-mismatch` check, the `csrf_token` hidden input, the theme toggle, or any existing `id`/`name`/`action`/`method` on `signup-form` — all remain byte-for-byte unchanged.

Files touched by the implementation phase: `frontend/templates/signup.html`, `frontend/static/css/styles.css`. This plan document itself makes no code changes.

---

## Phase 1 — Baseline Verification (pre-change)

**Goal:** Confirm the current state matches the spec's description before making any change.

**Steps:**
1. Start the app: `uv run backend/app/main.py`, confirm listening on `http://localhost:3001`.
2. Confirm `GET /signup` currently renders no strength-meter markup:
   ```
   curl -s http://localhost:3001/signup | grep -i "strength\|pwd-meter\|pwd-checklist"
   ```
   Expected (pre-fix): no output.
3. Confirm the current `#signup-form` structure in `frontend/templates/signup.html` matches lines 53–83 (username/email/password/confirm_password groups, `csrf_token` hidden input, submit button) — see the file as read for this plan.
4. Confirm `backend/app/api/routes/auth.py`'s `signup_post()` signature is unchanged from its current state (`username`, `email`, `password`, `csrf_token` — all `Form(...)`) — this plan adds no field to it.

No code is modified in this phase.

---

## Phase 2 — CSS: Design Tokens and Meter/Checklist Styles

**Goal:** Apply NFR-04, NFR-05 from the spec — additive tokens mirrored across both themes, reusing existing radius/text tokens where possible.

**File:** `frontend/static/css/styles.css`

### 2.1 Add strength-level color tokens to `:root` and `[data-theme="dark"]`

These are new tokens only — no existing token in either block is renamed or removed, matching the exact pattern the dark-mode-toggle feature already established (`.claude/specs/dark-mode-toggle.md` FR-02, NFR-04).

**Before** (`:root` block, light theme — ends with `--font-family`):
```css
    --font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
}
```

**After:**
```css
    --font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;

    --strength-weak: #dc2626;
    --strength-fair: #f59e0b;
    --strength-good: #ca8a04;
    --strength-strong: #16a34a;
    --strength-track: #e2e6f2;
    --meet-text: #16a34a;
    --unmet-text: var(--text-muted);
}
```

**Before** (`[data-theme="dark"]` block, ends with `--shadow-focus` per the existing dark-mode-toggle addition):
```css
    --shadow-focus: 0 0 0 3px rgba(92, 107, 192, 0.25);
}
```

**After:**
```css
    --shadow-focus: 0 0 0 3px rgba(92, 107, 192, 0.25);

    --strength-weak: #f87171;
    --strength-fair: #fbbf24;
    --strength-good: #eab308;
    --strength-strong: #4ade80;
    --strength-track: #2a2f42;
    --meet-text: #4ade80;
    --unmet-text: var(--text-muted);
}
```

*Rationale:* four distinct strength colors (red/amber/yellow-olive/green) give the meter and label a visually ordered progression in both themes; `--strength-track` is the unfilled portion of the bar; `--meet-text`/`--unmet-text` drive the checklist item colors, reusing the existing `--text-muted` token for the unmet state rather than inventing a new one (NFR-04).

### 2.2 Append meter/checklist component styles

Append a new section at the end of the file (after the existing `@media (max-width: 900px) { ... }` block, i.e., after the dark-mode-toggle feature's `.theme-toggle` dark-theme rules). This is purely additive — no existing selector is modified.

**Append:**
```css

/* ==========================================================================
   Password strength meter
   ========================================================================== */

.pwd-strength {
    margin-top: 8px;
    margin-bottom: 18px;
}

.pwd-strength-track {
    width: 100%;
    height: 6px;
    border-radius: var(--radius-tag);
    background: var(--strength-track);
    overflow: hidden;
}

.pwd-strength-fill {
    height: 100%;
    width: 0%;
    border-radius: var(--radius-tag);
    background: var(--strength-weak);
    transition: width 0.15s ease, background-color 0.15s ease;
}

.pwd-strength-fill[data-level="fair"] {
    background: var(--strength-fair);
}

.pwd-strength-fill[data-level="good"] {
    background: var(--strength-good);
}

.pwd-strength-fill[data-level="strong"] {
    background: var(--strength-strong);
}

.pwd-strength-label {
    display: block;
    font-size: 0.78rem;
    font-weight: 600;
    margin-top: 6px;
    color: var(--strength-weak);
}

.pwd-strength-label[data-level="fair"] {
    color: var(--strength-fair);
}

.pwd-strength-label[data-level="good"] {
    color: var(--strength-good);
}

.pwd-strength-label[data-level="strong"] {
    color: var(--strength-strong);
}

.pwd-checklist {
    list-style: none;
    margin: 8px 0 0 0;
    padding: 0;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 4px 12px;
}

.pwd-checklist li {
    font-size: 0.78rem;
    color: var(--unmet-text);
    display: flex;
    align-items: center;
    gap: 6px;
}

.pwd-checklist li .pwd-check-icon {
    font-size: 0.85rem;
    line-height: 1;
    width: 1em;
    text-align: center;
}

.pwd-checklist li[data-met="true"] {
    color: var(--meet-text);
}

@media (max-width: 900px) {
    .pwd-checklist {
        grid-template-columns: 1fr;
    }
}
```

*Notes:*
- `.pwd-strength-track`/`.pwd-strength-fill` reuse `--radius-tag` (existing token) rather than inventing a new radius (NFR-04).
- The checklist is a two-column grid on desktop, collapsing to one column at the same `900px` breakpoint the file's existing mobile media query already uses (NFR-06 — no new breakpoint introduced).
- `data-level`/`data-met` attribute selectors (rather than replacing classes) are used so the update script (Phase 3) only ever sets an attribute, never rewrites `className` strings — minimizing risk of clobbering other classes on the same element.

### 2.3 Verification for Phase 2

- Confirm no existing selector, property, or token in `styles.css` was deleted, renamed, or had its value changed — only new tokens and new rules were added.
- Confirm `:root` and `[data-theme="dark"]` each gained exactly the same six new custom properties (NFR-05).

---

## Phase 3 — Markup + Script in `signup.html`

**Goal:** Apply FR-01 through FR-09 from the spec.

**File:** `frontend/templates/signup.html`

### 3.1 Insert the meter/checklist markup beneath the Password field

**Before** (current Password `form-group`, immediately followed by Confirm Password's `form-group`):
```html
                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" autocomplete="new-password" required>
                </div>

                <div class="form-group">
                    <label for="confirm_password">Confirm Password</label>
```

**After:**
```html
                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" autocomplete="new-password" required>

                    <div class="pwd-strength" id="pwd-strength" aria-live="polite">
                        <div class="pwd-strength-track">
                            <div class="pwd-strength-fill" id="pwd-strength-fill" data-level="weak"></div>
                        </div>
                        <span class="pwd-strength-label" id="pwd-strength-label" data-level="weak">Weak</span>
                    </div>

                    <ul class="pwd-checklist" id="pwd-checklist">
                        <li data-met="false" data-rule="length">
                            <span class="pwd-check-icon" aria-hidden="true">&#10007;</span>
                            <span>At least 8 characters</span>
                        </li>
                        <li data-met="false" data-rule="lower">
                            <span class="pwd-check-icon" aria-hidden="true">&#10007;</span>
                            <span>One lowercase letter</span>
                        </li>
                        <li data-met="false" data-rule="upper">
                            <span class="pwd-check-icon" aria-hidden="true">&#10007;</span>
                            <span>One uppercase letter</span>
                        </li>
                        <li data-met="false" data-rule="digit">
                            <span class="pwd-check-icon" aria-hidden="true">&#10007;</span>
                            <span>One digit</span>
                        </li>
                        <li data-met="false" data-rule="special">
                            <span class="pwd-check-icon" aria-hidden="true">&#10007;</span>
                            <span>One special character</span>
                        </li>
                    </ul>
                </div>

                <div class="form-group">
                    <label for="confirm_password">Confirm Password</label>
```

*Notes:*
- Placed **inside** the existing Password `form-group` div (not a new top-level `form-group`), so it visually sits directly beneath the password input without adding another `margin-bottom: 18px` block — this avoids pushing Confirm Password down more than necessary (NFR-06).
- `aria-live="polite"` on the container announces strength-label changes to screen readers without being disruptive (supports NFR-03 alongside the icon+text combination).
- Each checklist `<li>` carries both `data-met="false"` (styling hook, toggled by script) and a `data-rule` identifier the script uses to target it — no `id` per item needed since they're queried via `querySelectorAll('[data-rule]')`.
- `&#10007;` (✗) is the initial "unmet" glyph; the script (3.2) swaps it to `&#10003;` (✓) when a rule becomes met, satisfying FR-03/NFR-03 (icon + color, not color alone).
- No `name` attribute exists anywhere in this block — nothing here is ever submitted as form data (FR-08).

### 3.2 Insert the scoring/update script

Insert a new `<script>` block immediately before the existing password-mismatch script (which currently is the last `<script>` block before `</body>`), so it does not interleave with or modify that script's contents (FR-09).

**Before:**
```html
    <script>
        const signupForm = document.getElementById('signup-form');
        const passwordInput = document.getElementById('password');
        const confirmInput = document.getElementById('confirm_password');
        const mismatchEl = document.getElementById('password-mismatch');

        function passwordsMatch() {
            return passwordInput.value === confirmInput.value;
        }

        confirmInput.addEventListener('input', function () {
            mismatchEl.style.display = (!passwordsMatch() && confirmInput.value.length > 0) ? 'block' : 'none';
        });

        signupForm.addEventListener('submit', function (e) {
            if (!passwordsMatch()) {
                e.preventDefault();
                mismatchEl.style.display = 'block';
            }
        });
    </script>
</body>
</html>
```

**After:**
```html
    <script>
        (function () {
            var passwordInput = document.getElementById('password');
            var fillEl = document.getElementById('pwd-strength-fill');
            var labelEl = document.getElementById('pwd-strength-label');
            var checklistItems = document.querySelectorAll('#pwd-checklist li[data-rule]');

            var RULES = {
                length: function (v) { return v.length >= 8; },
                lower: function (v) { return /[a-z]/.test(v); },
                upper: function (v) { return /[A-Z]/.test(v); },
                digit: function (v) { return /[0-9]/.test(v); },
                special: function (v) { return /[^A-Za-z0-9]/.test(v); }
            };

            function levelFor(metCount) {
                if (metCount <= 1) return 'weak';
                if (metCount <= 2) return 'fair';
                if (metCount <= 4) return 'good';
                return 'strong';
            }

            function levelLabel(level) {
                return { weak: 'Weak', fair: 'Fair', good: 'Good', strong: 'Strong' }[level];
            }

            function levelFillPercent(level) {
                return { weak: 20, fair: 45, good: 70, strong: 100 }[level];
            }

            function update() {
                var value = passwordInput.value;
                var metCount = 0;

                checklistItems.forEach(function (item) {
                    var rule = item.getAttribute('data-rule');
                    var met = RULES[rule](value);
                    if (met) metCount += 1;
                    item.setAttribute('data-met', met ? 'true' : 'false');
                    item.querySelector('.pwd-check-icon').innerHTML = met ? '&#10003;' : '&#10007;';
                });

                var level = value.length === 0 ? 'weak' : levelFor(metCount);
                fillEl.setAttribute('data-level', level);
                fillEl.style.width = value.length === 0 ? '0%' : levelFillPercent(level) + '%';
                labelEl.setAttribute('data-level', level);
                labelEl.textContent = levelLabel(level);
            }

            passwordInput.addEventListener('input', update);
            update();
        })();
    </script>

    <script>
        const signupForm = document.getElementById('signup-form');
        const passwordInput = document.getElementById('password');
        const confirmInput = document.getElementById('confirm_password');
        const mismatchEl = document.getElementById('password-mismatch');

        function passwordsMatch() {
            return passwordInput.value === confirmInput.value;
        }

        confirmInput.addEventListener('input', function () {
            mismatchEl.style.display = (!passwordsMatch() && confirmInput.value.length > 0) ? 'block' : 'none';
        });

        signupForm.addEventListener('submit', function (e) {
            if (!passwordsMatch()) {
                e.preventDefault();
                mismatchEl.style.display = 'block';
            }
        });
    </script>
</body>
</html>
```

*Notes:*
- This is a **separate, self-contained IIFE** — it declares its own `passwordInput` local variable via `var` inside its own function scope, so it does not collide with the pre-existing script's `const passwordInput` (that script keeps its own separate `const passwordInput = document.getElementById('password')` lookup, untouched) — both scripts independently query the same DOM element by `id`, which is safe and requires no shared state (FR-09: the existing script's contents are copied through completely unmodified).
- `RULES` implements exactly the five FR-01 criteria: `length >= 8` (inclusive boundary, EC-03), `[a-z]`, `[A-Z]`, `[0-9]`, and "special" defined as "not a letter and not a digit" (`[^A-Za-z0-9]`) — this naturally covers punctuation, symbols, and non-ASCII/Unicode characters as "special" without throwing (EC-04), since JS regex `.test()` never throws on arbitrary string input, satisfying EC-04/EC-05.
- `levelFor()` implements the FR-04 monotonic mapping: 0–1 criteria → Weak, 2 → Fair, 3–4 → Good, 5 → Strong. This is monotonic by construction (more met criteria never decreases the level) and is documented here as the concrete thresholds referenced by spec AC-03.
- `value.length === 0` is special-cased to force `weak`/`0%` regardless of `metCount` (which would otherwise also be 0, so this branch is actually redundant with `levelFor(0) === 'weak'` — kept explicit for readability and to guarantee EC-01's "no item met by default" reads unambiguously in code).
- `update()` is called once synchronously after being defined (in addition to being bound to `input`), so the checklist/meter reflect the field's actual value immediately on script execution — covers the case where a browser autofills the password field before the user's first keystroke.
- No `submit` listener is added by this script (FR-07) — only `input`. The pre-existing script's own `submit` listener (password-match gating) is copied through unmodified, immediately after this new script block.
- No new field is read from or written to `FormData`/the form's submission — this script never touches `signupForm` at all (FR-08).

### 3.3 Verification for Phase 3

- Confirm `#signup-form`'s `action="/signup" method="POST"`, the `csrf_token` hidden input, and all four existing field `id`/`name` attributes are unchanged (FR-09, TC-13).
- Confirm the pre-existing password-mismatch script block is present afterward, byte-for-byte identical to its pre-change content (FR-09, TC-12).
- Confirm no `name` attribute was added anywhere inside the new markup block (FR-08, TC-11).
- Confirm no `preventDefault()` or `submit` event listener appears in the new script (FR-07, TC-10).

---

## Phase 4 — Static Review Against Spec Requirements

**Goal:** Before running the app, verify the diff satisfies every FR/NFR without side effects.

**Checklist:**
- [ ] FR-01: five checklist items present (length, lower, upper, digit, special).
- [ ] FR-02: all updates bound to the password field's `input` event.
- [ ] FR-03/NFR-03: met/unmet distinguished by icon glyph + color, not color alone.
- [ ] FR-04: `levelFor()` monotonic across weak/fair/good/strong.
- [ ] FR-05: both a text label and a visual bar are present and update together.
- [ ] FR-06: empty password → all unmet, "Weak"/0% fill.
- [ ] FR-07: no `submit` listener, no `preventDefault()`, in the new script.
- [ ] FR-08: no new `name`d input, no change to `FormData`/submitted fields.
- [ ] FR-09: `username`/`email`/`confirm_password`/`csrf_token` fields, theme toggle, and the pre-existing password-mismatch script are byte-for-byte unchanged.
- [ ] NFR-01: no new dependency, no `<script src>`.
- [ ] NFR-02: no `fetch`/`XMLHttpRequest` in the new script.
- [ ] NFR-04/NFR-05: new CSS tokens added to both `:root` and `[data-theme="dark"]`; existing tokens/radii reused where applicable.
- [ ] NFR-06: checklist collapses to one column at the existing `900px` breakpoint; no overlap with Confirm Password.
- [ ] `git diff` (once implemented) touches only: `frontend/templates/signup.html`, `frontend/static/css/styles.css`.
- [ ] `git diff -- backend/app/` and `git diff -- frontend/templates/login.html frontend/templates/dashboard.html` show no output.

---

## Phase 5 — Functional Verification (post-change)

**Goal:** Execute the verification steps from `.claude/specs/pwd-str-meter.md` §10 against the modified code.

1. Restart the app:
   ```
   uv run backend/app/main.py
   ```
2. **Checklist and meter present (AC-01):**
   ```
   curl -s http://localhost:3001/signup | grep -o 'id="pwd-strength-label"'
   curl -s http://localhost:3001/signup | grep -c 'data-rule='
   ```
   Expected: first command prints a match; second prints `5`.
3. **Manual browser check (AC-02, AC-03, TC-01–TC-09):**
   - Open `http://localhost:3001/signup`. Confirm all 5 checklist items show `✗` and the label reads "Weak" with an empty/near-empty bar.
   - Type `abc` — confirm only "One lowercase letter" flips to `✓`; label stays "Weak" or moves to "Fair" per the 2-criteria threshold (only 1 met here, so "Weak").
   - Clear and type a 7-character password with no other criteria (e.g. `abcdefg`) — confirm "At least 8 characters" is `✗`.
   - Add one more character (`abcdefgh`) — confirm it flips to `✓`.
   - Clear and type `Str0ng!Pass` — confirm all 5 items show `✓` and label reads "Strong" with a full/near-full bar.
   - Delete the `0` — confirm "One digit" flips back to `✗` and the label downgrades (per `levelFor`, 4 met → "Good").
4. **No submission blocking, no new field (AC-04, AC-05, TC-10, TC-11):**
   - With DevTools Network tab open, fill username/email with valid unique values, password `x`, confirm password `x`, submit.
   - Confirm the request is `POST /signup` and its form body contains exactly `username`, `email`, `password`, `csrf_token` — no strength-related field.
   - Confirm the response is the same redirect-to-`/login` (or duplicate-username failure) behavior as before this feature.
5. **Backend and other templates untouched (AC-06, TC-15, TC-16):**
   ```
   git diff -- backend/app/ frontend/templates/login.html frontend/templates/dashboard.html
   ```
   Expected: no output.
6. **Existing signup behaviors preserved (AC-07, TC-12, TC-13):**
   - Confirm password-mismatch inline message still appears/disappears correctly when Password/Confirm Password differ.
   - Confirm submitting `/signup` with a missing/invalid `csrf_token` still returns `403` (re-run `.claude/specs/csrf-protection-fix.md` §10 step 5/6 against `/signup`).
7. **Theme-aware rendering (AC-08, TC-14):**
   - Toggle dark mode via the existing header button; confirm the meter/checklist remain legible and the toggle itself behaves exactly as documented in `.claude/specs/dark-mode-toggle.md`.
8. **Login page unaffected (TC-15):**
   ```
   curl -s http://localhost:3001/login | grep -c 'pwd-strength\|pwd-checklist'
   ```
   Expected: `0`.

---

## Rollback Plan

If Phase 5 verification fails (e.g., legitimate signup flow breaks, or an unrelated file is affected), revert the two touched files:
```
git checkout -- frontend/templates/signup.html frontend/static/css/styles.css
```
No other file requires rollback since none other is touched.
