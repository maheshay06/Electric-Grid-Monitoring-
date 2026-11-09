# 04 · Delivery Plan, Test Plan and Demo Runbook

**Product:** Electric Grid Monitoring and Control System using ML
**Depends on:** `01-PRD.md`, `02-Frontend-Design-Spec.md`, `03-Backend-and-System-Architecture.md`
**Status:** Draft for review · Effort is in working hours, not dates (no deadline was given; add yours in §9).

---

## 1. Where we are

| Area | State | Evidence |
|---|---|---|
| Backend API, rules, commands, users, SMS (mock), Demo Mode | ✅ Built | 59 passing tests |
| ML pipeline (synthetic data) | ✅ Built | 5 tests, ≈ 96.95 % on synthetic data only |
| Dashboard (single feeder, responsive) | ✅ Built | Builds, all pages render in Demo Mode, relay flow verified with simulated ACK |
| Portable VS Code setup | ✅ Built | Clean install from the copied folder passed |
| Documentation | ✅ Files 1–4 | This set |
| **ESP32 firmware on real hardware** | ❌ **Not verified** | Never compiled or flashed |
| **Real Twilio SMS** | ❌ **Not verified** | Mock only |
| Front-end automated tests | ❌ None | — |
| Final report alignment | 🔲 Pending | See §8 |

**The honest critical path to a credible demo is: hardware bring-up → real SMS → rehearsal.** Everything else is polish.

## 2. Milestones

| M | Name | Outcome (exit criteria) | Effort |
|---|---|---|---|
| **M0** | Baseline frozen | Code in git; tag `v0.9-demo-ready`; all tests green; docs 01–04 approved | 2 h |
| **M1** | Hardware bring-up | Firmware compiles; flashes; real V and I on the dashboard; calibration measured against a multimeter | 8–12 h |
| **M2** | Control loop on hardware | Trip and Restore acknowledged by the real ESP32; pushbutton logged; Wi-Fi drop and power-cycle behave | 6–8 h |
| **M3** | Real SMS | One real alert reaches a verified phone; repeat suppression observed | 2–3 h |
| **M4** | Fault drill | Forced under/over-voltage and overcurrent produce fault + ML warning + SMS | 3–4 h |
| **M5** | UX polish | Top-bar fix, local fonts, chart data table, reduced-motion, contrast audit (design spec §10) | 6–8 h |
| **M6** | Quality gate | Front-end smoke tests; security review pass; CI runs tests | 6–8 h |
| **M7** | Demo rehearsal and report | Two full rehearsals; backup plan tested; report matches the product | 6–10 h |

Total ≈ 40–55 h. M1–M4 are mandatory; M5–M6 are recommended; M7 is mandatory.

## 3. Work breakdown

### M0 — Baseline
1. `git init`, `.gitignore` already excludes secrets, DB, venv, node_modules; first commit; tag.
2. Run the full test pass on a clean clone (setup task → tests → build).
3. Resolve the PRD open questions and architecture decisions (PRD §12, Arch §11).

### M1 — Hardware bring-up (highest risk)
1. Install Arduino IDE or PlatformIO; ESP32 board package; libraries the sketch includes (LiquidCrystal I²C).
2. Copy `config.h.example` → `config.h`; set Wi-Fi, server LAN IP, device key from `seed.py`.
3. **Fix compile errors** (expect some; the sketch was never built).
4. Wire per the pin table: GPIO34 (V), GPIO35 (ACS712 through 10k/10k), GPIO25 relay (active-LOW), GPIO26 button, GPIO32 red LED, LCD on 21/22.
5. Serial monitor: check raw ADC, then calibrate `V_RATIO`, `I_ZERO_V`, `I_SENS_V_PER_A` against a multimeter at three loads.
6. Confirm telemetry reaches `/api/device/telemetry` (device shows ONLINE; values within ±2 % of the meter).
7. **Safety check before any load:** never above 5–6 V; ADC pins never above 3.3 V.

### M2 — Control loop
1. Trip and Restore from the dashboard; observe `PENDING → SENT → ACKED` and relay click.
2. Pull the Wi-Fi: pushbutton still trips; 3 s hold restores; device returns ONLINE after reconnect.
3. Unplug the device mid-command: UI shows TIMEOUT, never success.
4. Reboot: BOOT event recorded; relay state reported correctly.
5. Measure end-to-end latency (tap → ack) and record it.

### M3 — Real SMS
1. Twilio trial account; verify your phone; set `TWILIO_*` in `backend/.env`.
2. Admin → Alerts → add recipient → **Send test**.
3. Enable alerts; force an overcurrent; confirm one SMS; confirm the repeat window suppresses duplicates.
4. Confirm Demo Mode sends nothing.

### M4 — Fault drill
For each of UV, OV, OC: apply the condition on the bench (adjustable supply or load), then verify fault opens after 2 readings, ML class matches, SMS arrives, fault closes after recovery. Record screenshots.

### M5 — UX polish (see Design Spec §10)
Top-bar overflow at 768–1024 px; self-host Inter and JetBrains Mono; chart table alternative; `prefers-reduced-motion`; contrast fixes; optional dark mode.

### M6 — Quality gate
Add Vitest + React Testing Library smoke tests (render each page, relay flow with a mocked store); Playwright run of the demo path; `pip-audit` and `npm audit`; GitHub Actions or a local script running pytest + build; remove stray files (`pip.log`, `uv.log`, old DB).

### M7 — Rehearsal and report
Two full run-throughs (§6); update the report with screenshots, measured calibration and latency; state limitations exactly as in PRD §10.

## 4. Test plan

| Layer | What | Tool | Status |
|---|---|---|---|
| Unit/API | Auth, validation, command lifecycle, safety, demo, ML contract, firmware contract, SMS, users | pytest (59) | ✅ |
| ML | Dataset, training, prediction | pytest (5) | ✅ |
| Front-end build | Type-check and bundle | `npm run build` | ✅ |
| Front-end component | Pages render; relay flow; role gating | Vitest | 🔲 M6 |
| End-to-end (demo) | Login → toggle relay → simulated ACK → fault scenario | Playwright | 🔲 M6 |
| Hardware | Calibration, control loop, Wi-Fi loss, reboot | Manual bench | 🔲 M1–M2 |
| Alerting | Real SMS, repeat window | Manual | 🔲 M3 |
| Security | Roles, token revocation, lockout | pytest ✅; audit tools 🔲 | partial |
| Usability | 375 / 768 / 1280 px, touch targets | Checklist in Design Spec §11 | partial |

### Acceptance matrix (what an examiner can verify)

| Requirement | Test | Pass criteria |
|---|---|---|
| FR-1/2 live values | Change load; watch dashboard | Value within 2 % of multimeter, ≤ 3 s lag |
| FR-5/6 ack-only success | Trip with the device unplugged | UI shows TIMEOUT, state unchanged |
| FR-10 two-reading rule | Single-sample spike | No fault; sustained → fault |
| FR-13 SMS | Force overcurrent | SMS in ≤ 10 s, no duplicate within 15 min |
| FR-16 ML advisory | Force fault | Card shows Warning/Fault; relay does not move |
| FR-19 revocation | Admin deactivates a logged-in user | Next request from that user is rejected |
| FR-24 Demo | Toggle Demo | Banner, SIM tags, no SMS |
| G5 touch | 375 px viewport | No horizontal scroll; controls ≥ 44 px |

## 5. Risk register

| # | Risk | P | Impact | Mitigation | Owner |
|---|---|---|---|---|---|
| R1 | Firmware fails to compile or behaves differently | High | Critical | Start M1 first; keep Demo Mode as fallback | You |
| R2 | ACS712 noise masks small currents | High | Medium | Use ≥ 0.3 A test load; state the limit | You |
| R3 | Wi-Fi at the venue blocks client-to-client traffic | Medium | High | Bring a phone hotspot or travel router; test there beforehand | You |
| R4 | PC IP changes, so the ESP32 can't find the server | Medium | High | Static DHCP lease; print IP on the LCD; check before the demo | You |
| R5 | Twilio trial limits or no internet | Medium | Medium | Verified number; screenshot of an earlier SMS as evidence | You |
| R6 | Relay ack mistaken for contact feedback | Medium | Medium | Keep wording; mention in viva | You |
| R7 | Silent code changes (as seen during this project) | Medium | High | Git + tests before every demo | You |
| R8 | Windows long path breaks scikit-learn | Low | Medium | Run from a short path (`C:\GridMonitor`) | Setup script |
| R9 | ML questioned for synthetic data | Medium | Medium | Label everywhere; present as proof of pipeline; plan real-data retrain | You |

## 6. Demo runbook (15 minutes)

**Night before:** pull latest, run tests and build; flash firmware; charge tablet and phone; confirm IP; send one test SMS; export screenshots as backup; copy folder + zip to a USB drive.

**On stage**
1. (1 min) Dashboard on tablet: title, grid NORMAL, live V and A from the real ESP32.
2. (2 min) Vary the load; show the voltage/current bars and charts react.
3. (2 min) Tap relay switch → confirm → **say "it moves only when the ESP32 acknowledges"** → ACK appears → relay clicks.
4. (2 min) Force undervoltage: fault card, ML "Warning", SMS buzzes on phone.
5. (1 min) Unplug the ESP32, tap trip → TIMEOUT message (proves honesty rule).
6. (1 min) Press the physical button; show PUSHBUTTON event in the log.
7. (2 min) Admin tour: users, thresholds, audit trail.
8. (1 min) Toggle Demo Mode: banner and SIM tags.
9. (3 min) Questions; show the architecture slide and limitations.

**Fallbacks:** hardware dead → Demo Mode and say so; no Wi-Fi → phone hotspot; no SMS → show the SMS log and the earlier screenshot; backend crash → restart task *Run everything* (≈ 15 s).

## 7. Backlog beyond v1

| Priority | Item |
|---|---|
| P1 | Contact-position feedback input; Alembic; structured logging |
| P1 | Retrain ML on real recorded data; show real-vs-synthetic metrics |
| P2 | HTTPS reverse proxy; per-IP rate limits; PostgreSQL |
| P2 | Dark mode; PWA install on tablet; multilingual UI |
| P3 | Multi-feeder return (backend already supports it); e-mail alerts; delivery receipts; 2FA |

## 8. Report alignment checklist

- [ ] Title uses "Electric Grid Monitoring and Control System using ML" (UI already does).
- [ ] Block diagram matches Architecture §1.
- [ ] Pin table matches firmware; calibration values are the measured ones.
- [ ] ML section states synthetic data and shows the metrics file.
- [ ] Safety rules (PRD §6) listed as design requirements with the test that proves each.
- [ ] Limitations section = PRD §10.
- [ ] Screenshots: dashboard, relay ACK, fault + SMS, Demo banner.

## 9. Decisions and inputs needed

1. **Demo date and viva date** (to turn effort into a calendar).
2. Which hardware is ready now: ESP32, sensors, relay, LCD, power supply, test loads?
3. Will the venue have Wi-Fi you control?
4. Do you want me to start with **M0 + M1 support** (compile-check and fix the firmware sketch where possible, since I can't flash it) or **M5 polish** first? Recommended: M0 → M1.
