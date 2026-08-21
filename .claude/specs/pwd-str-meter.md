# Software Specification Document (Implementation Addendum)

## Vulnerable Web Application — Password Strength Meter

**Version:** 1.0.0
**Companion Documents:** `docs/PRD.md`, `docs/TDD.md`, `.claude/specs/app-foundation.md`, `.claude/specs/dark-mode-toggle.md`, `.claude/specs/bcrypt-password-hashing.md`

---

## 1. Overview / Purpose

This document specifies a real-time password strength indicator on the signup form (`frontend/templates/signup.html`). As the user types into the **Password** field, the page displays (a) a strength level — Weak / Fair / Good / Strong — with a visual meter, and (b) a live checklist of five criteria (minimum length 8, one lowercase letter, one uppercase letter, one digit, one special character), each shown as met or unmet and updating on every keystroke.

This is a **purely advisory, client-side UX affordance**. It helps a student choose a stronger password by giving immediate feedback; it does not enforce, block, or reject anything. No password policy is introduced anywhere in the request/response cycle — `POST /signup` continues to accept any non-empty password exactly as it does today, hashed via bcrypt per `.claude/specs/bcrypt-password-hashing.md`. The feature is additive only: no existing markup, script, route, or vulnerability is modified.

---

## 2. Scope & Non-Goals

### In Scope
- A visual strength meter (bar/segments) and a text label (Weak/Fair/Good/Strong) beneath the **Password** field on the signup form only.
- A live checklist of the five stated criteria, each rendered with a met/unmet visual state, updating on every `input` event on the password field.
- Client-side-only scoring logic (vanilla JS, no library), styled with new CSS additions in `frontend/static/css/styles.css` scoped to signup's existing form structure.

### Non-Goals / Explicitly Out of Scope
- **No server-side password policy.** `backend/app/services/auth_service.py`'s `signup()` is not modified; it continues to accept any non-empty password. This feature does not add minimum-length, character-class, or any other validation to the server.
- **No blocking of form submission.** The meter and checklist are advisory only — an unmet criterion (or a "Weak" rating) does **not** disable the submit button, does **not** call `preventDefault()`, and does **not** stop the existing standard `<form method="POST">` submission described in `app-foundation.md` §3.1. A user may submit a weak password exactly as they could before this feature existed.
- **No change to the login page.** `frontend/templates/login.html` has no password-creation flow (only a password field used for authentication against an existing account) and is not touched.
- **No change to `confirm_password` behavior.** The existing password-match check (`password-mismatch` field-error, in `signup.html`'s existing inline script) is untouched and continues to run independently of this feature.
- **No new dependency, no build step.** Implemented with plain CSS and a `<script>` block following the same inline-script convention already used in this file (theme toggle, password-match check).

### Vulnerability Status — All 8 Remain in Their Current (Already-Remediated) State

This feature is layered on top of a codebase where all 8 original vulnerabilities have already been fixed (see `CLAUDE.md`'s Vulnerability Map). It touches only signup's client-side markup/CSS/JS and must not alter any of the following:

| # | Vulnerability | Status | Effect of this feature |
|---|---|---|---|
| 1 | SQL Injection | Remediated (`auth_service.py`, parameterized queries) | Unaffected — no query code touched. |
| 2 | Stored XSS | Remediated (`html.escape()` on `{{username}}` in `/welcome`) | Unaffected — `/welcome` and `auth.py` are not touched. |
| 3 | Reflected XSS | Remediated (`/search`, parameterized query + escaping) | Unaffected — `/search` is not touched. |
| 4 | Session Hijacking | Remediated (env-sourced `SECRET_KEY`, `https_only`, `max_age`) | Unaffected — no session/middleware code touched. |
| 5 | Weak Password Storage | Remediated (bcrypt, work factor ≥ 12) | Unaffected — `security.py`'s hashing is untouched; the meter scores the **plaintext value in the browser only**, before it is ever submitted, and has no bearing on how the submitted password is hashed server-side. |
| 6 | Exposed Database | Remediated (session check on `/download/db`) | Unaffected — not touched. |
| 7 | No Rate Limiting | Remediated (`slowapi`, 5/minute on `/login` and `/signup`) | Unaffected — `signup_post()`'s decorator and signature (beyond what CSRF already added) are not touched. |
| 8 | CSRF | Remediated (session-stored token on `/login`/`/signup`) | Unaffected — the existing `csrf_token` hidden input and its value are not touched; this feature adds markup elsewhere in the same form. |

---

## 3. Affected Files

| File | Change |
|---|---|
| `frontend/templates/signup.html` | Adds a strength-meter bar, a strength-level label, and a five-item criteria checklist beneath the **Password** field; adds a new inline `<script>` block that scores the password on every `input` event and updates this markup. |
| `frontend/static/css/styles.css` | Adds new, additive CSS rules (and dark-theme token overrides) for the meter bar, its four strength colors, the strength label, and the checklist items' met/unmet states. |

**Inspected but must NOT be modified:**

- `frontend/templates/login.html` — no password-creation flow; out of scope.
- `frontend/templates/dashboard.html` — no password field; out of scope.
- `backend/app/api/routes/auth.py` — `signup_page()`/`signup_post()` are untouched; no new form field is submitted to the server by this feature (the meter reads the existing `password` input's value directly via the DOM, it does not add a new named input).
- `backend/app/services/auth_service.py` — `signup()`'s validation/business logic is untouched; no password policy is added.
- `backend/app/core/security.py` — bcrypt hashing untouched.
- No dependency is added to `backend/pyproject.toml`, the root `pyproject.toml`, or any frontend package manifest (none exists in this project).

---

## 4. Functional Requirements

### FR-01: Live Criteria Checklist
Beneath the **Password** field, render a checklist of exactly five items, each corresponding to one criterion:
1. At least 8 characters
2. At least one lowercase letter (`a`–`z`)
3. At least one uppercase letter (`A`–`Z`)
4. At least one digit (`0`–`9`)
5. At least one special character (any character that is not a letter or digit, e.g. `!@#$%^&*` etc.)

### FR-02: Real-Time Updates
Each checklist item's visual state (met/unmet) must update on every `input` event fired on the `#password` field — i.e., as the user types or deletes characters, with no perceptible delay and no need to blur the field or submit the form.

### FR-03: Met/Unmet Visual Distinction
A met criterion must be visually distinguishable from an unmet one (e.g., a check mark vs. a plain/empty marker, plus a color difference) and must also be distinguishable via text content or an ARIA-exposed state, not color alone (see NFR-03).

### FR-04: Strength Level Computation
A strength level must be computed from the same five criteria and mapped to exactly four levels, ordered least to most strong: **Weak**, **Fair**, **Good**, **Strong**. The mapping must be monotonic: meeting strictly more of the five criteria never produces a lower-ranked level than meeting fewer (an empty password is always Weak).

### FR-05: Strength Meter Display
The current strength level must be shown both as a short text label ("Weak" / "Fair" / "Good" / "Strong") and as a segmented/proportional visual bar whose filled portion and color reflect the level, updating on the same `input` event as the checklist (FR-02).

### FR-06: Empty-Field Initial State
When the password field is empty (page just loaded, or the user has cleared it), the checklist shows all five items as unmet and the strength meter/label shows the "Weak" (or empty/neutral) state — no item is shown as met by default.

### FR-07: No Submission Gating
Neither the strength level nor the checklist state may disable the submit button, intercept the `submit` event, or otherwise prevent the form from submitting. `signup-form`'s existing submission path (client-side password-confirmation check → standard `<form method="POST">` submission, per `app-foundation.md` §3.1 and §6.1) is preserved exactly as-is; this feature only adds a sibling `input` listener, never a `submit` listener.

### FR-08: No New Submitted Field
The meter's computed strength level and checklist state must not be sent to the server — no new hidden input, no additional `Form(...)` field on `signup_post()`, and no request payload change of any kind. The feature is entirely a browser-side read of the existing `#password` input's `.value`.

### FR-09: No Regression to Existing Markup or Behavior
The existing `username`, `email`, `password`, `confirm_password` fields (their `id`s, `name`s, and `required` attributes), the `csrf_token` hidden input, the password-mismatch script, the theme toggle, and the form's `action`/`method` attributes must remain byte-for-byte unchanged in structure and behavior; only additive markup (the meter/checklist block and its inline script) and additive CSS may be introduced.

---

## 5. Non-Functional Requirements

### NFR-01: No Framework, No Build Step, No New Dependency
Implemented with vanilla JavaScript in a new inline `<script>` block in `signup.html` (following the existing convention already used for the theme toggle and password-match check) and plain CSS in `styles.css` — no external library, no `<script src>` to a CDN, no new package manifest entry.

### NFR-02: Client-Side Only, No Network Requests
Scoring and rendering happen entirely in the browser on the `input` event; no `fetch()`, `XMLHttpRequest`, or other network call is introduced by this feature.

### NFR-03: Accessible State, Not Color-Only
Each checklist item's met/unmet state must be conveyed through more than color alone (e.g., a glyph/icon change plus text, or an `aria-live`/`aria-label` update), so the feature remains usable without relying on color perception. The strength label's text content (not just the meter's fill color) is the primary conveyor of the strength level.

### NFR-04: Consistent Visual Language
New colors/spacing must reuse the existing design tokens in `styles.css` (`--radius-input`, `--text-primary`, `--text-secondary`, `--text-muted`, existing font sizes) wherever they fit; any new tokens this feature requires (e.g., strength-level colors) are added additively to `:root` and mirrored under `[data-theme="dark"]`, following the exact pattern already established by the dark-mode-toggle feature (`.claude/specs/dark-mode-toggle.md` FR-02) — no existing token is renamed, removed, or repurposed.

### NFR-05: Theme-Aware
The meter, label, and checklist must render legibly in both the light and dark themes introduced by the dark-mode-toggle feature, without requiring the user to interact with the theme toggle for correctness — colors are sourced from CSS custom properties that already flip under `[data-theme="dark"]`.

### NFR-06: No Layout-Breaking Regression
Adding this block beneath the Password field must not visually overlap, clip, or push the Confirm Password field's label off-screen in either the desktop split-screen layout or the mobile stacked layout described in `app-foundation.md` §5.6.

### NFR-07: Minimal Diff
The change is limited to `signup.html` and `styles.css`. No other file is modified.

---

## 6. Success Paths

**SP-01 — Typing a weak password**: User focuses `#password` and types `abc` → checklist shows only "At least 8 characters" and "at least one lowercase" as unmet/met appropriately (3 chars is unmet for length; lowercase is met; upper/digit/special unmet) → strength label reads "Weak".

**SP-02 — Typing a strong password**: User types `Str0ng!Pass` (11 chars, has upper, lower, digit, special) → all five checklist items show as met → strength label reads "Strong" and the meter shows a full/near-full fill.

**SP-03 — Progressive typing**: User types a password one character at a time → the checklist and strength label update after every keystroke, without requiring blur or form submission (FR-02).

**SP-04 — Deleting characters**: User who has typed a strong password then deletes characters (e.g., removes the digit) → the corresponding checklist item flips back to unmet and the strength label/meter downgrades accordingly, on the same `input` event.

**SP-05 — Submitting despite a weak password**: User types a password meeting zero or few criteria and clicks "Sign Up" (with matching `confirm_password`) → the form submits exactly as it does today; `auth_service.signup()` is called and a new user row is created if the username is unique — the meter never blocks this (FR-07).

**SP-06 — Theme toggle interaction**: User switches to dark mode via the existing toggle while the meter/checklist are visible → all new elements remain legible (adequate contrast) without any additional user action.

---

## 7. Edge Cases

**EC-01 — Empty password field on page load**: Checklist shows all five items unmet; strength label shows "Weak" (or an equivalent neutral/empty state); no error styling is shown for an empty field on initial load (this is not a validation error, it's an unstarted state).

**EC-02 — Password consisting only of special/whitespace characters**: e.g. `!!!!!!!!` (8 special characters) → "at least 8 characters" and "at least one special character" are met; lowercase/uppercase/digit remain unmet; strength label reflects exactly 2 of 5 criteria met (Weak or Fair per the FR-04 mapping).

**EC-03 — Password exactly at the length boundary**: a 7-character password shows "at least 8 characters" unmet; an 8-character password shows it met — the boundary is inclusive (`length >= 8`).

**EC-04 — Non-ASCII/Unicode characters**: a password containing a Unicode letter (e.g., `é`) or emoji is scored using JavaScript's standard string semantics (`.length`, regex character classes) without throwing an error; such characters are treated as "not lowercase a–z / not uppercase A–Z / not digit / not special" in a best-effort sense consistent with the regexes defined in FR-01 — no crash, no blocked input.

**EC-05 — Extremely long input**: a very long pasted string (e.g., thousands of characters) is scored without noticeable UI lag or error, since the criteria checks are simple length/regex operations over the string.

**EC-06 — Paste event**: a password pasted via clipboard (not typed character-by-character) still triggers the `input` event per standard browser behavior, so the checklist/meter update immediately after a paste, not only after subsequent typing.

**EC-07 — JavaScript disabled**: with JavaScript disabled entirely, the meter/checklist markup (if rendered server-side as static HTML) either does not appear or appears in its static default (unmet) state and never updates — the form remains fully submittable via plain HTML, since FR-07/FR-08 guarantee no submission-path dependency on this script.

**EC-08 — Interaction with password-mismatch check**: the existing `confirm_password` mismatch message (unrelated to this feature) continues to appear/disappear based solely on the `password`/`confirm_password` equality check already implemented — this feature's checklist/meter are not consulted by that logic and do not alter its behavior (FR-09).

---

## 8. Acceptance Criteria

**AC-01 — Checklist present and correct**: Given the signup page is loaded, when the Password field is inspected, then a five-item checklist for length/lowercase/uppercase/digit/special-character is present beneath it.

**AC-02 — Real-time updates**: Given a user types into the Password field, when each keystroke is entered, then the checklist and strength label/meter update immediately (same `input` event), with no requirement to blur or submit.

**AC-03 — Strength levels correct**: Given passwords constructed to meet 0, 1–2, 3–4, and all 5 criteria respectively, when scored, then they map to Weak, Weak/Fair, Fair/Good, and Strong respectively, per a documented, monotonic FR-04 mapping (exact thresholds defined in the implementation plan).

**AC-04 — No submission blocking**: Given a password meeting none of the five criteria and a matching `confirm_password`, when the form is submitted, then the existing standard POST to `/signup` occurs exactly as before this feature, unblocked by strength/checklist state.

**AC-05 — No new submitted data**: Given the browser's network request for `POST /signup` is inspected, when compared to the pre-feature request, then it contains exactly the same fields (`username`, `email`, `password`, `csrf_token`) with no additional strength/checklist-related field.

**AC-06 — Existing vulnerabilities/fixes untouched**: Given `backend/app/**` in its entirety, when diffed against its pre-feature state, then no file under `backend/app/**` shows any change — all 8 already-remediated vulnerabilities remain exactly as remediated (per the table in §2), and no code path was reintroduced or altered.

**AC-07 — Existing signup behaviors preserved**: Given the existing password-mismatch check, CSRF token field, and theme toggle on `signup.html`, when this feature is added, then all three continue to function exactly as they did before (unchanged markup/IDs/scripts, per FR-09).

**AC-08 — Theme-aware rendering**: Given the dark theme is active (via the existing toggle), when the meter/checklist are visible, then they render with adequate contrast and correct colors sourced from the themed CSS custom properties (NFR-05).

---

## 9. Test Cases

| ID | Scenario | Precondition | Expected Result |
|---|---|---|---|
| TC-01 | Empty password on load | Signup page freshly loaded | All 5 checklist items show unmet; strength label shows "Weak"/neutral |
| TC-02 | Weak password | Type `abc` | Only the lowercase criterion is met; length/upper/digit/special unmet; label "Weak" |
| TC-03 | Length boundary — 7 chars | Type a 7-character password with no other criteria met | "At least 8 characters" shows unmet |
| TC-04 | Length boundary — 8 chars | Type an 8-character password with no other criteria met | "At least 8 characters" shows met |
| TC-05 | All criteria met | Type `Str0ng!Pass` | All 5 checklist items show met; label "Strong" |
| TC-06 | Progressive typing | Type a strong password one character at a time | Checklist/label update after every keystroke |
| TC-07 | Deletion downgrades strength | Start from a Strong password, delete the digit character | Digit criterion flips to unmet; label downgrades accordingly |
| TC-08 | Paste triggers update | Paste a password via clipboard instead of typing | Checklist/label update immediately after the paste |
| TC-09 | Special-character-only password | Type `!!!!!!!!` (8 chars) | Length and special-character criteria met; others unmet |
| TC-10 | Submission not blocked — weak password | Password meets 0 criteria, `confirm_password` matches | Form submits via standard POST to `/signup`; server responds exactly as pre-feature (redirect to `/login` on unique username) |
| TC-11 | No new network field | Any password value, form submitted | `POST /signup` request body contains only `username`, `email`, `password`, `csrf_token` — no strength/checklist field |
| TC-12 | Password-mismatch check unaffected | Password and Confirm Password differ | Existing `password-mismatch` message still appears exactly as before, independent of meter state |
| TC-13 | CSRF token unaffected | Signup page loaded | Hidden `csrf_token` input still present with a non-empty value; `POST /signup` without a valid token still returns `403` per `.claude/specs/csrf-protection-fix.md` |
| TC-14 | Theme toggle unaffected | Toggle to dark mode with meter/checklist visible | Meter/checklist remain visible and legible; toggle behavior otherwise unchanged from `.claude/specs/dark-mode-toggle.md` |
| TC-15 | Login page unaffected | `GET /login` | No strength meter/checklist markup present; page identical to pre-feature state |
| TC-16 | Backend fully unaffected | Any test in this table executed | `git diff -- backend/app/` shows no output |
| TC-17 | Unicode input does not crash | Type a password containing `é` or an emoji | No JavaScript error is thrown; checklist/label update to some deterministic (documented) state |

---

## 10. Verification Steps

1. From the project root, start the application:
   ```bash
   cd backend && uv sync
   uv run backend/app/main.py
   ```
2. Open `http://localhost:3001/signup`. Confirm the Password field has a checklist of 5 items and a strength meter/label beneath it, all showing an unmet/"Weak" initial state.
3. Type `abc` into Password — confirm only the lowercase item flips to met, and the label reads "Weak".
4. Clear the field and type `Str0ng!Pass` — confirm all 5 items flip to met and the label reads "Strong".
5. Delete the last few characters (removing the digit and/or special character) — confirm the corresponding items flip back to unmet and the label downgrades.
6. Open browser DevTools → Network tab. Fill in a valid unique username/email, a password meeting zero criteria (e.g. `x`), and a matching Confirm Password. Submit the form.
   - Confirm the request is a standard POST to `/signup` and inspect its form body: confirm it contains only `username`, `email`, `password`, `csrf_token` (no strength-related field).
   - Confirm the server's response behavior (redirect to `/login` on success, or the existing duplicate-username failure page) is unchanged from before this feature.
7. Toggle dark mode (existing header toggle) and confirm the meter/checklist remain legible.
8. Confirm `frontend/templates/login.html` is byte-for-byte unchanged (`git diff -- frontend/templates/login.html` shows no output) and no file under `backend/app/` shows any diff:
   ```
   git diff -- frontend/templates/login.html backend/app/
   ```
   Expected: no output.
9. Re-run the CSRF verification from `.claude/specs/csrf-protection-fix.md` §10 (steps 5–6) to confirm `POST /signup` still requires a valid `csrf_token` — unaffected by this feature.
