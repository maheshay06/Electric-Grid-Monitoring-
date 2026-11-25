

# Electric Grid Monitoring and Control System using ML

A full-stack monitoring and control platform for the final-year project *"Electric Grid Monitoring and Control System using ML"* (ESP32 hardware) (5 V DC feeder prototype, ESP32 DevKit V1).

| Layer | Tech | Folder |
|---|---|---|
| Dashboard | React, Vite, TypeScript, Tailwind CSS, Recharts, Lucide, React Router | `frontend/` |
| API + database | FastAPI, Pydantic, SQLAlchemy, SQLite, JWT, WebSocket | `backend/` |
| Fault classification | Python, Pandas, NumPy, scikit-learn, Joblib | `ml/` |
| Device firmware | ESP32 Arduino C++ | `firmware/grid_monitoring/` |

## Read this first: what is real and what is not

This project follows the honesty rules of your report. They are enforced in code, not just in this text.

- **The dashboard shows a single feeder** (Feeder 1, the only one with hardware). The backend still stores its extra feeder rows, but the UI ignores them.
- **Demo Mode data is simulated.** A banner reads *"DEMO MODE — SIMULATED DATA, NOT LIVE HARDWARE MEASUREMENTS"* on every page, and every simulated row is flagged in the database. Live and simulated data are never mixed in a query or a chart. With Demo Mode off and no ESP32, the app shows "No live data" — it never falls back to fake readings.
- **The ML model is trained on synthetic data.** Its metrics describe performance on generated samples, not on your hardware. Do not quote them as real-world accuracy. Retrain on properly measured, labelled data before making any real claim.
- **ML is advisory only.** No code path turns a prediction into a relay command (the command API has no "source" field and the AI router does not import the command service). Threshold fault detection also only raises alerts and notifications; it never trips the relay.
- **Trip/Restore success is shown only after the ESP32 acknowledges.** The feeder state in the UI is always what the device last reported. A command that is never acknowledged ends as `TIMEOUT` with the state unchanged.
- **The acknowledgement means "the ESP32 drove GPIO25".** Your current hardware has no relay contact feedback, so contact closure itself is not verified (report §3.7).
- **SMS alerts use Twilio and are OFF until you configure and enable them.** They are never sent for Demo Mode / simulated data. "Sent" means Twilio accepted the message; delivery receipts are not tracked.
- **The ACS712-5A is poor at LED-level currents** (~9 mA per ADC count). Calibrate against a multimeter and treat tiny currents as unreliable.
- The prototype is **5 V DC only. Never connect it to 240 V AC mains.**

## Architecture

```
ESP32 (Feeder 1) --HTTP: telemetry, heartbeat, events, command ack--> FastAPI --> SQLite
       ^                                                                |  |
       +------------------ GET /device/commands/next (poll) <-----------+  +--> scikit-learn (advisory)
                                                                        |
Browser (React) <---- REST (authoritative state) + WebSocket (change signal) ---+
Demo simulator (server side, only when Demo Mode is on) ----> same pipeline, rows flagged is_simulated
```

- The ESP32 never accepts inbound connections: it polls for commands, so no port needs opening on the device.
- The WebSocket carries only "something changed" messages; the browser re-fetches the real state over REST.
- Command lifecycle: `PENDING → SENT → ACKED | FAILED | TIMEOUT`.

## Folder structure

```
grid-monitor/
├── backend/        FastAPI app (app/), seed.py, requirements.txt, .env.example, tests in app/tests
├── frontend/       React app (src/api, components, pages, layouts, context)
├── ml/             generate_dataset.py, train_model.py, predict.py, config.json, data/, models/, tests/
└── firmware/       grid_monitoring/grid_monitoring.ino, config.h.example
```

## Prerequisites

- Python 3.11+ (developed on 3.13), Node.js 20+ and npm
- Arduino IDE 2.x with the ESP32 board package (Espressif), for the firmware
- A multimeter for calibration

> **Windows tip:** keep the project in a short path such as `D:\grid-monitor`. scikit-learn's DLLs fail to load from very long directory paths (`WinError 206`).

## Run in VS Code on any PC (portable setup)

1. Install **VS Code**, **Python 3.10 - 3.13** (tick *Add to PATH*) and **Node.js 20+**.
2. Copy this whole folder to the new PC. Use a **short path** such as `C:\GridMonitor` (very long Windows paths break scikit-learn).
   Do **not** copy `.venv`, `node_modules`, `backend/.env` or `*.db` - they are machine specific and are not in this folder.
3. In VS Code: **File > Open Workspace from File...** > `GridMonitor.code-workspace`, and accept the recommended extensions.
4. **Terminal > Run Task > Setup (first time)**. It creates `.venv`, installs the pinned backend packages, writes `backend/.env` with a fresh random `JWT_SECRET`, asks you for the first admin ID and password, seeds the database (the Feeder 1 device key is printed once), and runs `npm install`.
   (macOS / Linux: `bash scripts/setup.sh` does the same.)
5. **Terminal > Run Task > Run everything**, then open <http://localhost:5173>.

Other tasks in the same menu: *Backend: run tests*, *Backend: seed database*, *Frontend: type-check and build*. **Run > Backend: FastAPI (debug)** starts the API under the debugger.
Select the `.venv` interpreter (Python: Select Interpreter) if VS Code does not pick it automatically. Secrets stay in `backend/.env`, which is git-ignored and never copied by these scripts.

## Connect the ESP32 (LAN)

1. Backend must listen on the network: the VS Code task *Backend: run API* now uses `--host 0.0.0.0`. Allow port 8000 once (admin PowerShell): `New-NetFirewallRule -DisplayName "Grid Monitor API" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private`.
2. In `firmware/grid_monitoring/config.h` set `SERVER_BASE` to **this PC's** LAN address (`http://<PC-IP>:8000`), plus Wi-Fi and the device key printed by `seed.py` (or *Rotate* in Device Management). The ESP32's own address goes in `backend/.env` as `DEVICE_IP`.
3. Check the link: `powershell -ExecutionPolicy Bypass -File scripts\check-link.ps1 -DeviceKey gmk_...` (read-only). Device Management then shows *Online*, *Ping OK* and whether the ESP32's reported IP matches `DEVICE_IP`.
4. Turn **Demo Mode off** to see real data. Give the PC and the ESP32 fixed addresses in your router so they do not change.

## Setup

Open three terminals (backend, frontend, and one for the ML / firmware steps).

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # macOS/Linux: cp .env.example .env
```

Edit `.env`:

- `JWT_SECRET` — required, at least 32 characters. Generate one: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
- `SEED_ADMIN_OPERATOR_ID` and `SEED_ADMIN_PASSWORD` — your first admin account (password ≥ 10 characters with a letter and a digit, not containing the ID). There are **no built-in default credentials**.
- Leave the other values unless you need to change them (`CORS_ORIGINS`, timeouts, model paths).

Create the database, the South Substation, Feeders 1–3, Feeder 1's device and the admin user:

```bash
python seed.py
```

`seed.py` prints Feeder 1's **device API key once**. Copy it now (you can generate a new one later from *Device Management → Rotate*). Then start the API:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

Interactive API docs: <http://localhost:8000/docs>

### 2. ML model (optional until you want predictions)

```bash
cd ml
pip install -r requirements.txt   # same virtualenv is fine
python generate_dataset.py        # writes data/synthetic_dataset.csv + .meta.json (marked SYNTHETIC)
python train_model.py             # writes models/fault_classifier.joblib + metrics.json
python predict.py --voltage 4.1 --current 0.4
```

- Operating ranges, noise, sample counts and seed are configurable: edit `config.json` or use flags (`--samples-per-class`, `--seed`, `--noise-voltage`, `--noise-current`, `--config`).
- `train_model.py --algorithm dt|knn` trains a Decision Tree or KNN instead of the default Random Forest.
- The trainer refuses any dataset whose rows are not marked `SYNTHETIC`. If you later collect real labelled data, change that guard deliberately and update the disclaimers.
- A `.joblib` model only loads with the scikit-learn version that saved it. Retrain after upgrading.
- Restart the backend (or just retrain; it reloads when the file changes) so predictions appear.

Classes: `NORMAL`, `UNDERVOLTAGE`, `OVERVOLTAGE`, `OVERCURRENT`, `ABNORMAL CONDITION`.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The dev server proxies `/api` and `/ws` to `localhost:8000`. Sign in with the admin ID and password from `.env` and location ID `SS-SOUTH`.

Production build: `npm run build` (output in `frontend/dist`, serve it behind a reverse proxy that also forwards `/api` and `/ws`).

### 4. Try it without hardware (Demo Mode)

1. Sign in as the admin, go to **System Settings**, switch **Demo Mode** on.
2. Dashboard and charts fill with simulated data for the feeder, with the amber banner and SIM badges.
3. **Relay Control** has *Demo Controls*: inject undervoltage / overvoltage / overcurrent / abnormal patterns, simulate a pushbutton press, or simulate an ESP32 that never acknowledges.
4. Press **Trip Feeder** → confirm. You will see the command go `PENDING → SENT → ACKED`, with a **SIMULATED ACK** label, and only then the feeder turns to TRIPPED.
5. Switch Demo Mode off: simulated data disappears from every view and the live (empty) state returns.

Turning Demo Mode on deletes the previous *simulated* rows only; live data is never touched.

### 5. SMS alerts with Twilio (optional)

SMS follows report section 7.2: event-based, rate-limited, and worded so it never claims the relay physically opened or closed.

1. In the [Twilio console](https://console.twilio.com) copy your **Account SID** and **Auth Token**, and get a sender: a Twilio phone number, or a Messaging Service SID (`MG...`).
2. Put them in `backend/.env` (never commit this file) and restart the API:
   ```
   TWILIO_ACCOUNT_SID=AC...
   TWILIO_AUTH_TOKEN=...
   TWILIO_FROM_NUMBER=+1...          # or TWILIO_MESSAGING_SERVICE_SID=MG...
   SMS_TIMEZONE=Asia/Kolkata         # optional; timestamps in messages (default UTC)
   ```
3. Sign in as admin, open **Alerts → SMS alerts (Twilio)**: add recipients in E.164 format (e.g. `+919876543210`), use **Send test** (one real, billed SMS to one chosen number), then switch **Send SMS alerts** on.

What gets texted (plain ASCII, usually one 160-character segment):

| Event | Example wording |
|---|---|
| Controller boot | `GRID MONITOR: Feeder 1 controller started. Relay ENERGISED, status NORMAL. ...` |
| Under/over-voltage | `VOLTAGE ALERT GRID MONITOR: Feeder 1 OVERVOLTAGE. V=5.90V I=0.40A P=2.36W. 02-Nov 11:05 IST. Please inspect the supply.` |
| Overcurrent | `CURRENT ALERT GRID MONITOR: Feeder 1 OVERCURRENT. ...` |
| Trip / restore | `ALERT GRID MONITOR: Feeder 1 reported TRIPPED by the ESP32 (operator command). Relay state: RELEASED. ...` |
| ESP32 lost | `WARNING GRID MONITOR: Communication with the Feeder 1 controller (ESP32) is lost. ...` |

Behaviour and safeguards:

- A message is created only when its event is detected, and a trip/restore text is created only after the **ESP32 acknowledges / reports** it - requesting a trip texts nobody.
- The same fault, boot or offline event is texted at most once per `SMS_REPEAT_INTERVAL_S` (default 15 min); trips and restores use a shorter `SMS_STATE_CHANGE_INTERVAL_S` (60 s) so a real second trip is never swallowed. Suppressed events appear as `SKIPPED` in the message log.
- Messages go through an outbox table and a background worker, so Twilio problems never slow telemetry or relay control. Transient errors are retried with back-off (3 attempts); permanent ones (e.g. unverified number) are marked `FAILED` with Twilio's error code. An alert older than `SMS_MAX_AGE_S` (15 min) is dropped instead of sent late.
- Credentials come only from environment variables; the token is never returned by the API, stored in the database, or logged. Phone numbers are masked in the message log.
- **Twilio trial accounts** can only text numbers you have verified in the console, and prefix each SMS with a trial notice. Messaging to some countries needs extra Twilio registration; check the console.
- Each SMS costs money. The alert switch is off by default, and **Send test** needs an explicit confirmation.

### 6. ESP32 firmware

Wiring (from the report, Table 4.2 — do not change without review):

| GPIO | Function |
|---|---|
| 34 | DC voltage sensor OUT (never exceed 3.3 V) |
| 35 | ACS712-5A OUT via 10 kΩ / 10 kΩ divider |
| 25 | Relay IN, **active-LOW** |
| 26 | Pushbutton to GND (`INPUT_PULLUP`) |
| 32 | Red LED via 330 Ω |
| 21 / 22 | LCD SDA / SCL (I2C 0x27, 16×2) |

The green LED is wired through the relay COM/NO contacts, not to a GPIO. Common ground for everything; relay on a regulated 5 V supply. Safety checklist: report Appendix A.

Steps:

1. Arduino IDE → Library Manager: install **LiquidCrystal I2C** (Frank de Brabander) and **ArduinoJson 7.x**.
2. In `firmware/grid_monitoring/`, copy `config.h.example` to `config.h` and set Wi-Fi, `SERVER_BASE` (your PC's **LAN IP**, e.g. `http://192.168.1.50:8000` — not `localhost`) and `DEVICE_KEY`. `config.h` is git-ignored.
3. **Calibrate** `V_RATIO`, `I_ZERO_V`, `I_SENS_V_PER_A` against a multimeter (report §3.4–3.5, Table 6.1/6.2). The defaults are only the theoretical values.
4. Board: *ESP32 Dev Module*, upload at 115200 baud, open the Serial Monitor.
5. Allow inbound TCP 8000 in the PC firewall, and start the backend with `--host 0.0.0.0` so the ESP32 can reach it:
   `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`

Behaviour: short press while NORMAL trips; while TRIPPED, hold ≥ 3 s and release to restore. The button, relay, LEDs and LCD keep working with no Wi-Fi. The LCD's last character on the status page shows the link (`*` connected, `x` down, `K` device key rejected).

**The firmware has not been compiled or run on hardware in this repository's test environment.** Treat your first upload as a checkpoint and fill in the test sheets in the report (Tables 6.1–6.3).

## Roles and security

| Role | Can do |
|---|---|
| `viewer` | Read everything |
| `operator` | + acknowledge faults, send Trip/Restore, control demo scenarios |
| `admin` | + users, thresholds, Demo Mode toggle, SMS settings, register / rotate devices |

- Passwords: bcrypt. Login errors are identical for every failure; 5 failed attempts lock an operator ID for 15 minutes.
- JWTs are short-lived (`ACCESS_TOKEN_MINUTES`), the WebSocket authenticates with its first message (the token never appears in a URL), and the frontend keeps the token in `sessionStorage`.
- Device keys are stored only as SHA-256 hashes, shown once, rotatable.
- Telemetry is validated against the sensor's physical range (0–6 V, ±5 A, power ≈ V×I) and unknown fields are rejected before anything is stored.
- All secrets come from environment variables; `.env` and `config.h` are git-ignored.
- **User management** (admin, *User Management* in the sidebar): create users, change role / location / name / email, deactivate and reactivate, reset a password. Users are deactivated, never deleted, so the audit trail and command history stay intact. An admin cannot demote or deactivate themself, so at least one active admin always remains.
- New passwords need ≥ 10 characters, a letter and a digit, and must not contain the operator ID. The *Generate* button creates a random one; it is shown once for you to hand over.
- Every user can change their own password (profile menu → *Change password*). Changing a password, resetting it, changing a role, or deactivating an account **revokes every token that user already holds** (JWTs carry a per-user version), so the change takes effect immediately on all their sessions. Role changes and deactivation are also checked against the database on every request.
- Wrong-current-password and throttling replies use 400/429 (not 401), so the UI does not sign the user out; 5 wrong attempts lock password changes for 15 minutes.
- All user-management actions are written to the audit log (without passwords).
- For anything beyond a lab LAN: terminate TLS in a reverse proxy, use `https://` + a pinned CA in the firmware, restrict `CORS_ORIGINS`, and consider moving from SQLite (`DATABASE_URL` accepts other SQLAlchemy URLs; Postgres is untested here).

## Main API endpoints

Base `http://localhost:8000`, JWT `Authorization: Bearer …` unless noted. Full list at `/docs`.

| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout` |
| Monitoring | `GET /api/dashboard/summary`, `GET /api/feeders`, `GET /api/readings?feeder_id&range=1m|5m|15m|1h|24h` |
| Faults / alerts | `GET /api/faults`, `POST /api/faults/{id}/acknowledge`, `GET /api/notifications`, `POST /api/notifications/read-all` |
| Control | `POST /api/commands` (returns **202 PENDING**), `GET /api/commands` |
| AI | `POST /api/ai/predict`, `GET /api/ai/latest`, `GET /api/ai/history`, `GET /api/ai/metrics` |
| Users | `POST /api/auth/change-password` (self); admin: `GET/POST /api/users`, `PATCH /api/users/{id}`, `POST /api/users/{id}/reset-password`, `GET /api/users/locations` |
| Admin | `GET/PUT /api/settings`, `PUT /api/feeders/{id}/thresholds`, `GET/POST /api/devices`, `POST /api/devices/{id}/rotate-key` |
| SMS | `GET /api/sms/status`, `GET /api/sms/messages`; admin: `PUT /api/sms/enabled`, `GET/POST/DELETE /api/sms/recipients`, `POST /api/sms/test` |
| Demo | `GET /api/demo/state`, `POST /api/demo/scenario | drop-ack | pushbutton` |
| Live | `WS /ws/live` (first message `{"type":"auth","token":"…"}`) |
| Device (`X-Device-Key`) | `POST /api/device/telemetry | heartbeat | events`, `GET /api/device/commands/next`, `POST /api/device/commands/{id}/ack` |

## Tests

```bash
cd backend && python -m pytest app/tests     # auth, validation, command lifecycle, safety rules, demo mode, firmware contract, SMS (Twilio is mocked), user management and token revocation, database column migration
cd ml && python -m pytest tests              # dataset, training, prediction
cd frontend && npm run build                 # typecheck + production build
```

The backend suite includes `test_ai_model.py`, which needs `pandas` and `scikit-learn` (it is skipped if they are missing). The firmware contract test reads `grid_monitoring.ino` and checks that the pin map, relay polarity and JSON the sketch sends are accepted by the real API.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| SMS stays `QUEUED`/`FAILED` | Check the error in *Alerts -> Recent messages*: `20003` bad credentials, `21608` unverified trial number, `21211` invalid number. |
| Port 8000 already in use | Run the API on another port (`--port 8010`) and start the frontend with `set API_TARGET=http://localhost:8010` (PowerShell: `$env:API_TARGET="http://localhost:8010"`). |
| Backend exits with a validation error about `jwt_secret` | Set `JWT_SECRET` (≥ 32 chars) in `backend/.env`. |
| Login says "Invalid operator ID, password or location ID" | Run `python seed.py` with `SEED_ADMIN_*` set; location is `SS-SOUTH`. Locked out? Wait 15 min or restart the backend. |
| Page says "Cannot reach the backend" | Start uvicorn on port 8000 before `npm run dev`. |
| AI page says metrics unavailable / predict returns 503 | Run `ml/generate_dataset.py` then `ml/train_model.py`; keep `ml/` beside `backend/` or set `ML_MODEL_PATH`. |
| `WinError 206` importing scikit-learn | Project path is too long; move it to a short path. |
| ESP32: LCD shows `K` | Server rejected `DEVICE_KEY`. Re-run seed or rotate the key and update `config.h`. |
| ESP32: `x` link indicator, serial shows request errors | Wrong `SERVER_BASE` IP, firewall, backend not bound to `0.0.0.0`, or different Wi-Fi network. |
| Trip command stays `SENT` then `TIMEOUT` | Device offline or not polling. State is intentionally unchanged. |
| Current reads noisy / non-zero with no load | Re-measure `I_ZERO_V`; ACS712-5A resolution is ~9 mA. |
| `V: SENSOR ERR` / `I: SENSOR ERR` on LCD | Voltage or current outside physical range (0–8 V / ±5 A). Check voltage sensor GND and `S` pin (GPIO34), ACS712 5V supply and 10k/10k divider (GPIO35). If bench-testing without ACS712, set `I_ZERO_V` to 0.0f and `I_DEADBAND_A` to 0.1f in `config.h`. |
| Power shows 0.00 W or `---` | Power is $P = V \times I$. If load is disconnected or relay is tripped, $I = 0$ A so $P = 0$ W. If either sensor has an error, telemetry is paused until both sensors read within valid limits. |

## Mapping to the report

| Report item | Where |
|---|---|
| Table 4.2 pin map, active-LOW relay, 3 s restore hold, LCD pages | `firmware/grid_monitoring/grid_monitoring.ino` |
| Table 7.2 ML classes | `ml/generate_dataset.py`, `ml/train_model.py` |
| "Success only after the ESP32 acknowledges" | `backend/app/services/command_service.py`, `RelayControlPanel.tsx` |
| "Prediction must be validated before any control action" | no ML→command path; see `backend/app/routers/ai.py`, `test_safety_and_rules.py` |
| Event history with timestamps, fault log | `fault_events` table, Fault History page |
| Demo mode "never presented as real" | `demo_simulator.py`, `DemoBanner.tsx`, `is_simulated` columns |
| Table 7.1 SMS templates, repeat-alert interval | `backend/app/services/sms_service.py`, `sms_worker.py` |
| Table 8.1 *planned* items still open | ML-based automatic trip (deliberately not built), better current sensing |

## Known limitations

- Firmware untested on hardware; relay contact feedback does not exist in the current circuit.
- Single real feeder, single device; multi-feeder control is only exercised in Demo Mode.
- SMS goes through Twilio only (no GSM module); no delivery-receipt tracking, no inbound SMS commands. Database upgrades are limited to an automatic additive SQLite column migration (`app/migrate.py`; no Alembic), no email / SSO / two-factor login, no automatic purge of old live readings.
- The synthetic classifier cannot tell you anything about real faults on your hardware.
#   E l e c t r i c - G r i d - M o n i t o r i n g -  
 