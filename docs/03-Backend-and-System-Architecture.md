# 03 · Backend and System Architecture

**Product:** Electric Grid Monitoring and Control System using ML
**Depends on:** `01-PRD.md`, `02-Frontend-Design-Spec.md` · **Status:** Draft for review
**Legend:** ✅ built and tested · ⚠️ built, not verified on hardware / live service · 🔲 recommended

---

## 1. System context

```
 ┌──────────────┐  HTTP poll (1 s)   ┌─────────────────────────┐  REST + WebSocket  ┌────────────────┐
 │ ESP32 + HW   │ ─────────────────▶ │  FastAPI backend        │ ◀───────────────── │ React dashboard │
 │ V sensor     │ ◀───────────────── │  rules · commands · ML  │ ───────────────▶   │ (browser)       │
 │ ACS712-5A    │   X-Device-Key     │  SQLite · background    │   JWT (Bearer)     └────────────────┘
 │ Relay GPIO25 │                    │  tasks                  │
 └──────────────┘                    └───────────┬─────────────┘
                                                 │ HTTPS (httpx)
                                          ┌──────▼──────┐
                                          │ Twilio SMS  │
                                          └─────────────┘
```

| Part | Tech | Role |
|---|---|---|
| Firmware ⚠️ | ESP32 Arduino C++, FreeRTOS | Measure, report, poll commands, drive relay, local control |
| Backend ✅ | FastAPI, Pydantic v2, SQLAlchemy 2, SQLite | Single source of truth, safety rules, alerting |
| ML ✅ | scikit-learn Random Forest, joblib | Advisory classification, trained offline |
| Frontend ✅ | React, Vite, TypeScript, Tailwind, Recharts | Operator UI |
| SMS ⚠️ | Twilio REST via httpx | Alerts (mock-tested only) |

**Key architectural choice:** the ESP32 **polls** the server (it never accepts inbound connections). This works behind any home or campus NAT and keeps the device attack surface to zero open ports.

## 2. Backend layout ✅

```
backend/app/
  main.py        lifespan: create tables → additive migration → start background tasks
  config.py      pydantic-settings; refuses to start without JWT_SECRET (≥ 32 chars)
  database.py    engine, WAL + foreign keys for SQLite
  models.py      13 tables      schemas.py   request/response validation
  security.py    bcrypt, JWT, device-key hashing, login throttle
  deps.py        auth dependencies: current_user, role guards, current_device
  migrate.py     adds missing columns to an existing SQLite file
  routers/       thin HTTP layer (one file per area)
  services/      all logic: commands, rules, telemetry, ML, SMS, demo, heartbeat, ws
  tests/         59 tests
```

Rule: routers validate and authorise; **services decide**. No router contains business rules.

## 3. Data model ✅

| Table | Purpose | Notes |
|---|---|---|
| `locations` | Substation | SS-SOUTH |
| `users` | Operators | role, bcrypt hash, `token_version`, `is_active`, last login |
| `feeders` | Feeders + thresholds + reported relay/load state | UI uses feeder 1 only |
| `devices` | ESP32 registry | SHA-256 of API key, last heartbeat, firmware, RSSI, IP |
| `sensor_readings` | Time series | `is_simulated` flag; index on feeder + ts |
| `fault_events` | Rule events, trips, restores, offline | status ACTIVE / ACKNOWLEDGED / CLEARED; source RULE / OPERATOR / PUSHBUTTON / SYSTEM |
| `ai_predictions` | One row per reading | class, confidence, severity, input values |
| `relay_commands` | Command lifecycle | `device_id` nullable for demo commands |
| `notifications` | In-app alerts | `is_simulated` |
| `system_settings` | Key/value | demo_mode, sms_enabled |
| `audit_log` | Who did what | no secrets |
| `sms_recipients`, `sms_messages` | SMS outbox | status QUEUED / SENT / FAILED / SKIPPED |

Timestamps are stored UTC (custom `UTCDateTime` type). Migrations are additive only (`migrate.py`); there is no Alembic. 🔲 Adopt Alembic before any schema change that renames or drops columns.

## 4. API surface ✅

**Operator API** (JWT Bearer, role-guarded)

| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/login`, `GET /me`, `POST /logout`, `POST /change-password` |
| Monitoring | `GET /api/dashboard/summary`, `GET /api/feeders`, `GET /api/feeders/{id}`, `GET /api/readings?feeder_id&range` |
| Control | `POST /api/commands` (operator/admin), `GET /api/commands`, `GET /api/commands/{id}` |
| Faults | `GET /api/faults`, `POST /api/faults/{id}/acknowledge` |
| Notifications | `GET /api/notifications`, `POST /{id}/read`, `POST /read-all` |
| AI | `GET /api/ai/latest`, `/history`, `/metrics`, `POST /predict` |
| SMS | `GET /status`, `/messages` (any user); admin: `PUT /enabled`, recipients CRUD, `POST /test` |
| Admin | `GET/PUT /api/settings`, `PUT /api/feeders/{id}/thresholds`, `GET/POST /api/devices`, `POST /devices/{id}/rotate-key`, users: `GET/POST /api/users`, `PATCH /{id}`, `POST /{id}/reset-password`, `GET /users/locations` |
| Demo | `GET /api/demo/state`; operator/admin: `POST /scenario`, `/drop-ack`, `/pushbutton` |
| Live | `WS /ws/live` (first message `{type:"auth", token}`) |

**Device API** (header `X-Device-Key`)

| Endpoint | Purpose |
|---|---|
| `POST /api/device/telemetry` → 202 | `{voltage, current, power?, relay_state, uptime_s?}` |
| `POST /api/device/heartbeat` → 202 | firmware, RSSI, IP, uptime |
| `GET /api/device/commands/next` | 200 with the next command (marks it SENT) or 204 |
| `POST /api/device/commands/{id}/ack` | `{success, relay_state, error?}` |
| `POST /api/device/events` → 202 | `BOOT`, `PUSHBUTTON_TRIP`, `PUSHBUTTON_RESTORE` |

Health check: `GET /api/health`.

## 5. The safety-critical flows ✅

### 5.1 Command lifecycle (the heart of the product)

```
Operator taps switch ─▶ POST /api/commands ─▶ row PENDING (validated: role, device online, no duplicate in flight)
ESP32 polls          ─▶ GET /commands/next ─▶ row SENT
ESP32 drives GPIO25  ─▶ POST /commands/{id}/ack {success, relay_state}
Server               ─▶ ACKED only if success AND reported state matches the expected one
                         → feeder.relay_state updated FROM THE REPORT, TRIPPED/RESTORED event + notification
No ack within 10 s   ─▶ TIMEOUT (expire_stale) → UI shows "NOT acknowledged"
Wrong or failed ack  ─▶ FAILED
```

Guarantees: (1) the UI cannot change feeder state; only an accepted ack or a device report can. (2) A device can only ack its own SENT commands (404/409 otherwise). (3) The ack means "ESP32 drove the GPIO", not "contacts moved".

### 5.2 Telemetry path
Validate against physical limits (0–6 V, |I| ≤ 5 A, power ≈ V×I, no unknown fields) → store → mark device online → run rule engine → run ML → publish a WebSocket "telemetry" signal. Rejected frames return 422 and are not stored.

### 5.3 Rule engine
`OVERCURRENT` > `oc_threshold`; `UNDERVOLTAGE` < `uv_threshold`; `OVERVOLTAGE` > `ov_threshold`. A fault opens after **2 consecutive** violating readings and closes after **2 consecutive** clean ones. **It never trips the relay.** Thresholds validate as UV < nominal < OV.

### 5.4 ML
Offline: `generate_dataset.py` → `train_model.py` → `fault_classifier.joblib` + `metrics.json` (records the scikit-learn version; a model is tied to it). Online: `ai_service.predict(v, i, p)` per reading; result stored in `ai_predictions`. No import path connects ML to `command_service`; a test asserts it. The backend runs without a model file (UI shows "Awaiting data"). Accuracy ≈ 96.95 % **on synthetic data only**.

### 5.5 Heartbeat / offline
A background task marks a device OFFLINE after 15 s without telemetry or heartbeat, opens `DEVICE_OFFLINE`, and recovers on the next report.

### 5.6 SMS pipeline ⚠️
Event → `sms_service.enqueue` (checks configured + enabled + not simulated + repeat window) → one `sms_messages` row per active recipient → `sms_worker` sends via Twilio, retries transient errors with backoff, does not retry permanent ones, drops alerts older than `SMS_MAX_AGE_S`. Window: 15 min for the same event, 60 s for trips/restores. SENT = accepted by Twilio; no delivery receipts. Phone numbers are masked in API responses.

### 5.7 Demo Mode
Admin toggle. A server-side simulator writes labelled rows (`is_simulated = true`), keeps in-memory simulated feeder state, backfills 24 h, produces simulated ACKs after 1.8 s, and supports scenarios (UV, OV, OC, abnormal, dropped ACK, pushbutton). All reads filter by the current mode, so simulated and real data never mix; SMS is never sent.

## 6. Security model ✅

| Control | Implementation |
|---|---|
| Passwords | bcrypt (12 rounds); ≥ 10 chars, letter + digit, not containing the ID |
| Sessions | JWT (HS256, 60 min) with per-user `tv` claim; role, active state and `tv` re-checked on every request |
| Revocation | Password change/reset, role change, deactivation bump `token_version` |
| Brute force | 5 failures → 15 min lockout (login and change-password); equal-time handling for unknown users |
| Roles | admin / operator / viewer, enforced in dependencies, not in the UI |
| Device auth | `gmk_…` key, stored as SHA-256, shown once, rotatable, constant-time compare |
| Input | Pydantic `extra="forbid"`, physical range checks, E.164 phone check |
| WebSocket | Token in first message, never in the URL |
| Secrets | `.env`, git-ignored; token for Twilio treated as secret; audit log has no secrets |
| Transport | Plain HTTP on a trusted LAN is accepted for the prototype; firmware supports HTTPS with a pinned root CA |

🔲 Gaps: no rate limiting per IP, no CSRF concerns (Bearer tokens, not cookies), no HTTPS termination shipped, JWT secret rotation is manual, SQLite file is unencrypted.

## 7. Firmware contract ⚠️

| Item | Value |
|---|---|
| Pins | GPIO34 voltage sensor, GPIO35 ACS712 (via 10k/10k divider), **GPIO25 relay (active-LOW: LOW = energised)**, GPIO26 pushbutton, GPIO32 red LED, GPIO21/22 I²C LCD 0x27 |
| Timing | sample 500 ms, telemetry 1 s, heartbeat 5 s, command poll 1 s, HTTP timeout 2 s |
| Tasks | Network task on core 0; local control + sensing on core 1; queues for commands, acks, events |
| Local safety | Pushbutton works with Wi-Fi down; restore needs a 3 s hold; invalid sensor data is not sent as telemetry |
| Calibration | `V_RATIO`, `I_ZERO_V`, `I_SENS_V_PER_A` in `config.h`; must be measured on real hardware |
| Config | `config.h` (git-ignored) from `config.h.example`; server URL must be the PC's LAN IP |

A contract test checks that the JSON the firmware builds is accepted by the backend schemas. **The sketch has never been compiled or flashed.**

## 8. Configuration ✅

`backend/.env` keys: `JWT_SECRET`, `DATABASE_URL`, `CORS_ORIGINS`, `HEARTBEAT_TIMEOUT_S`, `COMMAND_TIMEOUT_S`, `SEED_ADMIN_*`, `ML_MODEL_PATH`, `ML_METRICS_PATH`, `TWILIO_*`, `SMS_*`. The `.env` is resolved relative to the backend folder. Ports: API 8000, UI 5173 (Vite proxies `/api` and `/ws`).

## 9. Non-functional analysis

| Concern | Status |
|---|---|
| Scale | Designed for 1 device at 1 Hz (~86 k rows/day). SQLite WAL handles this; 🔲 add retention/rollup for > 30 days |
| Latency | Poll interval bounds command delivery to ≈ 1 s plus the device's HTTP time |
| Availability | Single process; background tasks live inside it. If the server dies, the relay keeps its last state and local button control works |
| Observability | Audit log, command and fault tables; 🔲 structured logs and a `/metrics` endpoint |
| Testing | 59 backend tests (auth, validation, command lifecycle, safety, demo, ML contract, firmware contract, SMS, users), 5 ML tests |
| Deployment | Local PC for the demo; 🔲 container image and a reverse proxy with TLS if hosted |

## 10. Risks and recommendations

| # | Risk | Severity | Recommendation |
|---|---|---|---|
| 1 | Firmware never run on hardware | **High** | Bench-test: compile, flash, observe telemetry, trip/restore, Wi-Fi drop, power cycle |
| 2 | ACK ≠ contact position | High | Add an auxiliary contact or relay-coil feedback input; until then keep the wording |
| 3 | Real SMS untested | Medium | Send one test message to a verified number |
| 4 | Command poll adds up to ~1 s lag | Low | Acceptable; long-poll later if needed |
| 5 | SQLite and additive migrations | Medium | Alembic before further schema work |
| 6 | Extra feeder rows still exist in the DB | Low | Decide in review whether to remove them (PRD open question 1) |
| 7 | Security files were found changed on disk during this work (hash, settings, validators), then repaired | Medium | Keep tests in CI; protect against silent edits with version control |
| 8 | Plain HTTP between ESP32 and server | Medium on shared networks | Use a private LAN, or HTTPS with the pinned CA |

## 11. Decisions to confirm

1. Keep **polling** for the device (recommended) or move to MQTT?
2. Keep **SQLite** for v1 (recommended) or PostgreSQL now?
3. Remove feeders 2 and 3 from the database, or keep them hidden?
4. Add **Alembic** now or after the demo?
5. Should the server **ever** be allowed to trip automatically? Recommended: **no**, per the report.
