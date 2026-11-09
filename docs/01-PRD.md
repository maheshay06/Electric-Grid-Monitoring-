# 01 · Product Requirements Document (PRD)

**Product:** Electric Grid Monitoring and Control System using ML
**Version:** 1.0 (draft for review) · **Status:** Awaiting approval
**Context:** Final-year engineering project; 5 V DC educational prototype; one real feeder.

---

## 1. Summary

A web dashboard plus an ESP32 controller that lets an operator **watch** one feeder's voltage and current in real time, **trip or restore** its relay remotely, get an **advisory ML read** of grid health, and receive **Twilio SMS alerts** when something goes wrong.

One sentence: *"See the feeder, trust what you see, and act on it safely from a phone or tablet."*

## 2. Problem

Small substations and lab feeders are checked by hand. Faults (under/over-voltage, overcurrent) are noticed late, and switching a feeder needs someone on site. Existing SCADA is too heavy and costly for a college prototype, and generic IoT dashboards fake or hide the difference between "commanded" and "actually done".

## 3. Goals

| # | Goal | Measure |
|---|------|---------|
| G1 | Live visibility of voltage, current, power | Reading on screen ≤ 3 s after the ESP32 sends it |
| G2 | Safe remote control | Relay state shown **only** after the ESP32 acknowledges; 0 unacknowledged "success" messages |
| G3 | Early fault awareness | Rule engine opens a fault after 2 consecutive bad readings; SMS queued ≤ 10 s later |
| G4 | Advisory ML | Classifier labels every reading; never operates the relay |
| G5 | Usable on phone/tablet | All controls ≥ 44 px; no horizontal scroll at 375 px |
| G6 | Honest demo | Demo Mode data is always labelled; never mixed with real data |
| G7 | Runs on any PC | Setup in ≤ 15 min from a fresh clone, via one task in VS Code |

## 4. Non-goals (v1)

- Multiple feeders in the UI (the backend can store more; the UI shows one).
- Controlling real mains (240 V AC). The prototype is 5 V DC only.
- Automatic protective tripping by the ML model or the server. Only the operator trips.
- Delivery receipts for SMS, e-mail alerts, SSO, 2FA, password self-reset.
- Mobile native apps; multi-tenant / multi-site management.
- Replacing a certified protection relay.

## 5. Users and roles

| Role | Who | Can do |
|------|-----|--------|
| **Viewer** | Faculty, examiner, observer | See everything; change nothing |
| **Operator** | Student running the demo | + trip / restore relay, acknowledge faults |
| **Admin** | Project owner | + thresholds, Demo Mode, SMS recipients, devices & keys, user management |
| **Device** | The ESP32 | Sends telemetry/heartbeat, polls and acknowledges commands (own API key) |

Primary scenario: an operator on a tablet sees voltage sag, the card turns amber, an SMS reaches their phone, they open the app, tap the relay switch, confirm, and see "acknowledged by ESP32" only when the device really answers.

## 6. Non-negotiable rules (from the project report)

1. **Acknowledged-only success.** Trip/Restore is "done" only after the ESP32 acknowledges. The ack means *the ESP32 drove the GPIO*, not that contacts moved (no contact feedback exists). The UI says so.
2. **ML is advisory.** No code path lets a prediction create or send a command.
3. **Only Feeder 1 is real.** No simulated number is ever shown as live hardware data.
4. **Relay state comes from the device report**, never from the click.
5. **Demo Mode is loud:** banner "DEMO MODE — SIMULATED DATA, NOT LIVE HARDWARE MEASUREMENTS", SIM badges, and no SMS.
6. **Dataset is synthetic** and labelled so wherever the model's accuracy appears.
7. **Secrets never leave `.env`;** device keys are stored hashed and shown once.

## 7. Functional requirements

### 7.1 Monitoring
- FR-1 Show **voltage (voltage sensor, 5 V input)** and **current (ACS712-5A)** and derived **power (P = V×I)**, each with units, last-update time and a bar against its safe limit.
- FR-2 Real-time charts of voltage and current with dashed UV/OV/OC limits; ranges 1 m, 5 m, 15 m, 1 h, 24 h.
- FR-3 Grid status badge: NORMAL / FAULT CONDITION / TRIPPED / NO DATA.
- FR-4 If the device stops reporting for > 15 s, status becomes OFFLINE and values show "—".

### 7.2 Relay control
- FR-5 One large ON/OFF switch with a confirm dialog; role-gated (operator/admin).
- FR-6 Command lifecycle PENDING → SENT → ACKED / FAILED / TIMEOUT (10 s). While in flight the switch does not move.
- FR-7 Timeout shows "NOT acknowledged — verify on site".
- FR-8 Command history with who, when, status, acknowledgement time.
- FR-9 Local pushbutton on the device also works and is logged as source PUSHBUTTON.

### 7.3 Faults and alerts
- FR-10 Rule engine: 2 consecutive violating readings open an event; 2 clean readings close it. Types: UNDERVOLTAGE, OVERVOLTAGE, OVERCURRENT, TRIPPED, RESTORED, DEVICE_OFFLINE.
- FR-11 Fault log: search, filter by type/status, sort, paginate, export CSV, acknowledge.
- FR-12 In-app notifications with unread count.
- FR-13 **Twilio SMS** for faults, ESP32-reported trips/restores, boot and lost communication; repeat suppression (default 15 min), stale-alert drop, retries; never for simulated data. Dashboard shows armed/off state and the last triggered alerts. "SENT" means Twilio accepted it.
- FR-14 Admin manages recipients (E.164), master on/off, and can send a test SMS to one chosen number.

### 7.4 ML
- FR-15 Classes: NORMAL, UNDERVOLTAGE, OVERVOLTAGE, OVERCURRENT, ABNORMAL CONDITION from voltage, current, power.
- FR-16 Dashboard shows a health indicator (Healthy / Warning / Fault likely), confidence, and the "advisory only, synthetic data" label; detail page shows history, metrics and rule-vs-AI comparison.
- FR-17 Pipeline is reproducible: generate dataset → train → metrics saved with scikit-learn version.

### 7.5 Administration
- FR-18 Login with operator ID, password, location; 5 failures → 15 min lockout.
- FR-19 Admin creates users, changes role/location, deactivates, resets passwords; changes revoke existing sessions at once. Users are never deleted.
- FR-20 Everyone can change their own password.
- FR-21 Thresholds editable by admin with validation (UV < nominal < OV).
- FR-22 Device registry with rotate-key (key shown once).
- FR-23 Audit log of every control and admin action, without secrets.

### 7.6 Demo Mode
- FR-24 Admin toggle; server-side simulator produces labelled data, simulated ACKs and fault scenarios (UV, OV, OC, abnormal, dropped ACK, simulated pushbutton).

### 7.7 Firmware (ESP32)
- FR-25 Reads sensors, posts telemetry ~1 Hz, heartbeat, polls commands, acknowledges, active-LOW relay on GPIO 25, local control keeps working when Wi-Fi is down, 3 s hold to restore locally.

## 8. Non-functional requirements

| Area | Requirement |
|------|-------------|
| Performance | Dashboard update ≤ 3 s end-to-end on LAN; API p95 < 300 ms at 1 device |
| Reliability | Network loss never blocks local relay control; UI recovers by polling if WebSocket drops |
| Security | bcrypt passwords, JWT with revocation, hashed device keys, per-role endpoint checks, request validation against physical limits |
| Usability | Touch targets ≥ 44 px, readable at 375 px, status never conveyed by colour alone |
| Portability | Python 3.10–3.13, Node 20+, one setup task, no cloud dependency except optional Twilio |
| Maintainability | Small modules, typed API, automated tests (backend 59, ML 5), README |
| Honesty | Every simulated, synthetic or unverified item is labelled in the UI and docs |

## 9. Success criteria for the project demo

1. Live telemetry from the real ESP32 on the dashboard.
2. Trip and Restore each shown acknowledged by the ESP32 on stage.
3. A forced undervoltage raises a fault, an ML warning and an SMS to a verified phone.
4. Demo Mode works with no hardware and is clearly marked.
5. Examiner can read each claim in the report against a visible feature.

## 10. Risks and assumptions

| Risk / assumption | Mitigation |
|---|---|
| Firmware has **never been compiled or run on hardware** | Flash and test on the bench before anything else; use Demo Mode as a fallback |
| ACS712-5A resolves ~9 mA per ADC step, so LED-level loads read poorly | Say so in UI and report; use a larger test load |
| No contact feedback, so ack ≠ contacts moved | Wording everywhere; optional auxiliary contact input later |
| ML trained on synthetic data only | Label it; collect real readings for a v2 retrain |
| Twilio trial restrictions (verified numbers, prefix text) | Use verified phone; document |
| Real SMS never tested end-to-end (mock tests only) | Send one test SMS before the demo |
| SQLite, single server | Fine for one feeder; revisit for more |
| Windows long paths break scikit-learn | Short project path, setup script warns |

## 11. Current status (honest)

- **Built and tested:** backend API, rule engine, Demo Mode, commands, SMS (mocked), users, ML pipeline, single-feeder dashboard (builds and renders in demo).
- **Not verified:** firmware on hardware, real Twilio delivery, real-device latency, production deployment.

## 12. Open questions for review

1. Is the **UI single-feeder permanently**, or should the backend also be trimmed to one feeder?
2. Should the **ML label drive the dashboard colour**, or stay a separate advisory card (current)?
3. Do you want **SMS on ML warnings** too, or only rule-based faults (current)?
4. Is **internet access** available at the demo (Twilio, fonts)? If not, host fonts locally.
5. Who is the **audience**: examiners only, or real users after graduation? This decides how much hardening goes in v2.
6. Language/units: English only, SI units. Confirm.
