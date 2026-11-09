# 02 · Frontend Design Specification

**Product:** Electric Grid Monitoring and Control System using ML
**Depends on:** `01-PRD.md` · **Status:** Draft for review
**Legend:** ✅ built today · 🔲 recommended, not built yet

---

## 1. Design intent

The screen must answer three questions in under two seconds, from a tablet held in one hand:

1. **Is the grid OK?** (status, voltage, current)
2. **What does the ML think?** (advisory)
3. **What can I do about it?** (relay switch, alerts)

Principles:

| # | Principle | Consequence |
|---|-----------|-------------|
| D1 | **Truth over polish** | State comes from the device report. Simulated, synthetic and unverified items are labelled, always. |
| D2 | **One feeder, no clutter** | One hero, three sensor cards, three action cards, two charts, one log. Nothing repeats. |
| D3 | **Touch first** | Every control ≥ 44 px; primary actions reachable by thumb. |
| D4 | **Colour plus words** | Status is never colour alone (badge text, icons, labels). |
| D5 | **Danger needs intent** | Relay changes go through a confirm dialog and wait for the ESP32. |
| D6 | **Calm by default, loud on fault** | Quiet indigo/white surface; red and amber appear only when something is wrong. |

## 2. Visual language ✅

**Palette** (Tailwind tokens in `tailwind.config.js`)

| Token | Hex | Use |
|---|---|---|
| `navy-950/900/700` | `#0B1020` `#141B3A` `#2D3A7C` | Hero, headings, text |
| `brand` | `#6366F1` (dark `#4338CA`, light `#E0E7FF`) | Primary actions, active nav, voltage line |
| `accent` | `#06B6D4` | Gradient partner, progress bars |
| `surface` | `#F3F5FB` + soft radial glows | Page background |
| Status | emerald `#059669` normal · amber `#D97706` warning · red `#DC2626` fault/trip · slate `#64748B` offline/unknown · blue info/simulated ack |
| Chart | voltage indigo `#6366F1` · current orange `#EA580C` · power teal `#0F766E` · limits red dashed |

**Type:** Inter (UI), JetBrains Mono (numbers). Sizes: hero 24–30, page title 24, card title 16, value 36 mono, label 12 uppercase, helper 12.
**Shape:** cards `rounded-3xl`, controls `rounded-xl`, badges full pill. Shadow: one soft indigo-tinted elevation. Glass (blur) only on the top bar and bottom bar.
**Motion:** 150–300 ms transitions on bars and the switch, `active:scale-[.98]` on buttons, pulse only on active fault badges. 🔲 Respect `prefers-reduced-motion`.

## 3. Layout and responsiveness ✅

| Width | Behaviour |
|---|---|
| < 1024 px (phone, tablet) | Slide-over sidebar (hamburger) **and** a 5-item bottom tab bar: Dashboard · Live · Relay · AI · Alerts. Content gets 80 px bottom padding. |
| ≥ 1024 px | Fixed 288 px sidebar, no bottom bar. |
| Grids | Sensors 1 → 3 columns (md); actions 1 → 3 (lg); charts 1 → 2 (xl). |
| Banner | Amber Demo banner above everything when Demo Mode is on. |

Targets: no horizontal page scroll at 375 px (tables scroll inside their own card); touch targets ≥ 44 px; bottom bar ≥ 56 px.

## 4. Information architecture ✅

```
Login
App shell: Demo banner · Top bar · Sidebar / Bottom bar
 ├─ Dashboard            /            (hero view)
 ├─ Live Monitoring      /live
 ├─ Relay Control        /control
 ├─ AI Fault Prediction  /ai
 ├─ Fault History        /faults
 ├─ Analytics            /analytics
 ├─ Alerts               /alerts      (notifications + SMS settings)
 ├─ Device Management    /devices
 ├─ System Settings      /settings    (admin edits)
 └─ User Management      /users       (admin only)
```

🔲 Recommendation: group the last four under "Admin" in the sidebar and hide them from the bottom bar (already hidden) to reduce noise for viewers.

## 5. Screen specs

### 5.1 Login ✅
Two panels: brand panel (title, one-line purpose, 5 V safety note) and form (Operator ID, Password, Location). Errors inline, `role="alert"`. Lockout and wrong-password use the same wording. 🔲 Prefill location from last login.

### 5.2 Dashboard ✅ (the screen the examiner sees)
Top to bottom:

1. **Hero** — gradient panel: eyebrow "South Substation · Live feeder", H1 = project title, one line "Relay energised · load connected · updated 3 s ago", **Grid status** badge (NORMAL / FAULT CONDITION / TRIPPED / NO DATA).
2. **No-data notice** only if Demo is off and the device is silent.
3. **Sensor row (3 cards):**
   - *Voltage* — "Voltage sensor module · 5 V input", value, bar vs 6 V, "Nominal 5.0 V · safe 4.5–5.5 V". Bar turns red outside the band.
   - *Current* — "ACS712-5A current sensor", value, bar vs OC limit, note "low resolution at LED loads". Red above limit.
   - *Active power* — "Calculated P = V × I".
4. **Action row (3 cards):**
   - *Relay Control* — big ON/OFF switch (see 6.1).
   - *ML Grid Health* — Healthy / Warning / Fault likely, class name, confidence bar, "Random Forest · synthetic training data · advisory only".
   - *Twilio SMS Alerts* — Armed / Off / Not configured, recipients count, last 4 alerts with SENT / QUEUED / FAILED / SKIPPED.
5. **Real-time charts** — voltage and current with a range selector (1 m … 24 h) and dashed limits.
6. **Fault log** — search, type and status filters, sortable, 6 per page.

### 5.3 Live Monitoring ✅
Big numeric strip (V, A, W, last sample) + three full-width charts (280 px). Empty state when no data.

### 5.4 Relay Control ✅
Centered switch card, Demo Controls (only in Demo Mode), command history, feeder events.

### 5.5 AI Fault Prediction ✅
Synthetic-data warning strip → latest prediction card → "Rule engine vs AI" comparison → model metrics (accuracy, per-class, confusion matrix) → prediction history table. 🔲 Add a plain-language line: "Accuracy applies to synthetic data only."

### 5.6 Fault History, Analytics, Alerts, Devices, Settings, Users ✅
Table-and-form pages. Settings holds thresholds, Demo toggle, calibration notes. Alerts holds notification list and the admin SMS panel. Users has create / edit / deactivate / reset-password dialogs.

## 6. Key components

### 6.1 Relay switch ✅
- 160 × 80 px pill; knob shows ON / OFF or a spinner while a command is in flight.
- Position = **reported** relay state. A tap opens a confirm dialog; after confirming, the knob **does not move** until the ESP32 acknowledges (D5).
- Messages: in flight (blue), ACKED (green, "SIMULATED ACK" tag in demo), TIMEOUT (red, "verify on site"), offline (amber), read-only role (grey).
- Disabled when offline, in flight, or role is viewer.
- 🔲 Add haptic feedback (`navigator.vibrate`) on confirm for tablets.

### 6.2 Status badge ✅
Pill with dot + word; tones green / amber / red / grey / blue; pulse only for active fault or trip.

### 6.3 Sensor card ✅
Icon tile, label, hardware name, mono value + unit, progress bar, limit text, "SIM" tag in Demo.

### 6.4 ML health card ✅
Mapping: no prediction → grey "Awaiting data"; NORMAL → green "Healthy"; non-normal with Low/Medium → amber "Warning"; High/Critical → red "Fault likely".

### 6.5 SMS card ✅
Three states: Armed (configured + enabled), Off (configured, disabled), Not configured. Footnote: "SENT = accepted by Twilio, not delivered".

### 6.6 Tables, charts, dialogs ✅
Tables scroll within the card; sortable headers expose `aria-sort`. Charts have `role="img"` with a label. Confirm dialog traps focus. 🔲 Chart data table alternative for screen readers.

## 7. State matrix

| State | Hero badge | Cards | Relay switch | Banner |
|---|---|---|---|---|
| Live, normal | NORMAL (green) | values, bars normal | enabled | none |
| Live, fault active | FAULT CONDITION (amber, pulse) | offending bar red | enabled | none |
| Tripped | TRIPPED (red, pulse) | values ~0 A | OFF, enabled | none |
| Device offline | NO DATA (grey) | "—" | disabled + warning | notice card |
| Demo Mode | as above | "SIM" tags | enabled, "SIMULATED ACK" | amber banner |
| Backend unreachable | — | full-page "Cannot reach the backend", auto-retry | — | — |
| Viewer role | as above | as above | disabled, "read-only" | none |

## 8. Accessibility (WCAG 2.2 AA target)

✅ Semantic landmarks, labels on icon buttons, `role="status"/"alert"` for command and error messages, switch uses `role="switch"` with `aria-checked`, progress bars have names.
🔲 Contrast audit of amber-on-white badges and grey helper text; visible focus ring on dark hero; reduced-motion support; keyboard shortcut for emergency trip is **not** recommended (D5).

## 9. Content and microcopy rules

- Say "reported by ESP32", never "relay opened/closed".
- Say "advisory" next to every ML output.
- Say "simulated" next to every demo value.
- Numbers: voltage 2 decimals, current 3, power 2; time as local `hh:mm:ss`.

## 10. Known gaps and recommendations

| # | Gap | Priority |
|---|-----|---|
| 1 | Top bar is crowded at 768–1024 px (title + substation + health + ESP32 + clock) | Medium |
| 2 | Fonts load from Google; offline demo falls back to system fonts | Medium |
| 3 | No dark mode (control-room use) | Low |
| 4 | Charts have no table alternative | Medium |
| 5 | Production bundle is 650 kB; split routes | Low |
| 6 | No front-end automated tests (visual or component) | Medium |
| 7 | Relay card repeats on Dashboard and Relay Control (by design for speed) | Info |

## 11. Acceptance checklist

- [ ] 375 px, 768 px, 1280 px: no horizontal page scroll; bottom bar visible below 1024 px.
- [ ] Every button/input ≥ 44 px (inspect).
- [ ] Trip: switch stays until ACK, then flips; timeout shows the red warning.
- [ ] Demo Mode: banner, SIM tags, "SIMULATED ACK".
- [ ] Viewer cannot operate the switch; non-admin does not see User Management.
- [ ] Offline: values "—", switch disabled, notice shown.
- [ ] Tab through the Dashboard: every control reachable, focus visible.
