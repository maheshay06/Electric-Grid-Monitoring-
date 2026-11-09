/*
 * ESP32-Based Electric Grid Monitoring and Control System  --  Feeder 1 firmware
 * Board: ESP32 DevKit V1  (Arduino IDE: "ESP32 Dev Module")
 *
 * Libraries (Library Manager):
 *   - "LiquidCrystal I2C" by Frank de Brabander
 *   - "ArduinoJson" by Benoit Blanchon, version 7.x
 *   - ESP32 board package (Espressif) 2.0.x or 3.x   (WiFi, HTTPClient, Wire are bundled)
 *
 * Hardware (pin map from the project report, Table 4.2 -- do not change without review):
 *   GPIO34  DC voltage sensor OUT          (input only; never exceed 3.3 V)
 *   GPIO35  ACS712-5A OUT via 10k/10k divider
 *   GPIO25  Relay IN, ACTIVE-LOW           (LOW = energised = load connected = NORMAL)
 *   GPIO26  Pushbutton to GND, INPUT_PULLUP
 *   GPIO32  Red LED via 330 ohm            (ON = TRIPPED)
 *   GPIO21/22  LCD SDA/SCL, I2C 0x27, 16x2
 * The green LED is wired through the relay contacts (COM/NO) and is not on a GPIO.
 * Prototype is 5 V DC ONLY. Never connect it to 240 V AC mains.
 *
 * Behaviour
 *  - Local operation never depends on Wi-Fi or the server: the pushbutton, relay, LEDs and LCD
 *    run in loop() on core 1. All networking runs in a separate task on core 0.
 *  - Pushbutton: short press+release while NORMAL trips. While TRIPPED, hold >= 3 s then release restores.
 *  - Remote commands are only EXECUTED when the server hands them to this device (polling), and are
 *    only reported as done by an acknowledgement sent AFTER the relay pin has been driven.
 *    The ACK means "the ESP32 drove GPIO25". The current hardware has no contact-position feedback,
 *    so contact closure itself is not verified (see report, section 3.7).
 *  - Telemetry reports the relay state this firmware is actually driving, not what was requested.
 *  - Nothing here acts on machine-learning output. The ML classifier only runs on the server and is advisory.
 */
#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <LiquidCrystal_I2C.h>

#if __has_include("config.h")
#include "config.h"
#else
#error "Copy config.h.example to config.h and fill in your Wi-Fi, server URL, device key and calibration."
#endif

#define FIRMWARE_VERSION "1.0.0"

// ---------------- pins (report Table 4.2) ----------------
#define PIN_V      34
#define PIN_I      35
#define PIN_RELAY  25   // active-LOW
#define PIN_BTN    26   // INPUT_PULLUP
#define PIN_RED    32

#define ADC_SAMPLES        150
#define DEBOUNCE_MS        40
#define RESTORE_HOLD_MS    3000
#define MAX_VALID_VOLTAGE  6.0f   // matches the server's physical limit; anything above is a wiring/calibration fault
#define MAX_VALID_CURRENT  5.0f   // ACS712-5A range

LiquidCrystal_I2C lcd(0x27, 16, 2);

enum State : uint8_t { NORMAL, TRIPPED };
static State state = NORMAL;  // owned by loop(); never written from the network task

// ---------------- data shared between the two cores ----------------
struct Shared {
  float v = 0, i = 0, p = 0;
  bool valid = false;        // false until the first sane measurement
  bool relayEnergised = true;
} shared;
static SemaphoreHandle_t sharedMtx;

struct CmdMsg   { uint32_t id; bool trip; };
struct AckMsg   { uint32_t id; bool success; bool energised; };
enum EventType : uint8_t { EV_BOOT, EV_BTN_TRIP, EV_BTN_RESTORE };
struct EventMsg { EventType type; bool energised; };

static QueueHandle_t cmdQ, ackQ, eventQ;
static volatile bool netOk = false;       // last server request succeeded recently
static volatile bool keyRejected = false; // server answered 401: wrong DEVICE_KEY
static int lastStatus = 0;                // HTTP status of the most recent request (network task only)

// ---------------- helpers ----------------
static const char* relayWord(bool energised) { return energised ? "ENERGISED" : "RELEASED"; }

static float readPinVolts(int pin) {
  uint32_t sum = 0;
  for (int k = 0; k < ADC_SAMPLES; k++) sum += analogReadMilliVolts(pin);  // factory-calibrated mV
  return (sum / (float)ADC_SAMPLES) / 1000.0f;
}

static void applyOutputs() {
  const bool energised = (state == NORMAL);
  digitalWrite(PIN_RELAY, energised ? LOW : HIGH);  // active-LOW relay module
  digitalWrite(PIN_RED, energised ? LOW : HIGH);
  xSemaphoreTake(sharedMtx, portMAX_DELAY);
  shared.relayEnergised = energised;
  xSemaphoreGive(sharedMtx);
}

static void queueEvent(EventType t) {
  EventMsg m{t, state == NORMAL};
  xQueueSend(eventQ, &m, 0);  // dropped only if 8 events are already waiting
}

static void setState(State s, bool fromButton) {
  if (s == state) return;
  state = s;
  applyOutputs();
  Serial.printf("[STATE] %s (%s)\n", s == NORMAL ? "NORMAL" : "TRIPPED", fromButton ? "pushbutton" : "remote");
  if (fromButton) queueEvent(s == NORMAL ? EV_BTN_RESTORE : EV_BTN_TRIP);
}

// ---------------- measurement ----------------
static void measure() {
  const float vPin = readPinVolts(PIN_V);
  const float iPin = readPinVolts(PIN_I);
  float v = vPin * V_RATIO;
  float i = (iPin - I_ZERO_V) / I_SENS_V_PER_A;
  if (fabsf(i) < I_DEADBAND_A) i = 0;
  const bool sane = isfinite(v) && isfinite(i) && v >= 0 && v <= MAX_VALID_VOLTAGE && fabsf(i) <= MAX_VALID_CURRENT;

  xSemaphoreTake(sharedMtx, portMAX_DELAY);
  shared.valid = sane;           // an insane reading is never sent to the server
  if (sane) { shared.v = v; shared.i = i; shared.p = v * i; }  // P = V x I (report, section 3.6)
  xSemaphoreGive(sharedMtx);

  Serial.printf("V=%.3f V  I=%.3f A  P=%.3f W  state=%s  net=%s%s\n", v, i, v * i, state == NORMAL ? "NORMAL" : "TRIPPED",
                netOk ? "ok" : "down", sane ? "" : "  [SENSOR OUT OF RANGE - not sent]");
}

// ---------------- LCD (report section 3.9) ----------------
static void lcdLine(uint8_t row, const char* text) {
  char buf[17];
  snprintf(buf, sizeof(buf), "%-16s", text);
  lcd.setCursor(0, row);
  lcd.print(buf);
}

static void updateLcd(uint8_t page) {
  Shared s;
  xSemaphoreTake(sharedMtx, portMAX_DELAY);
  s = shared;
  xSemaphoreGive(sharedMtx);
  char a[24], b[24];
  switch (page) {
    case 0:
      snprintf(a, sizeof(a), "Voltage: %.2fV", s.v);
      snprintf(b, sizeof(b), "Current: %.2fA", s.i);
      break;
    case 1:
      snprintf(a, sizeof(a), "Power: %.2fW", s.p);
      snprintf(b, sizeof(b), "Load: %s", state == NORMAL ? "ON" : "OFF");
      break;
    default:
      snprintf(a, sizeof(a), "Grid Status:");
      snprintf(b, sizeof(b), "%s", state == NORMAL ? "NORMAL" : "TRIPPED");
      break;
  }
  if (!s.valid) snprintf(b, sizeof(b), "SENSOR ERR");
  lcdLine(0, a);
  lcdLine(1, b);
  // link indicator on the last character of line 1 of the status page only
  if (page == 2) { lcd.setCursor(15, 0); lcd.print(keyRejected ? 'K' : (netOk ? '*' : 'x')); }
}

// ---------------- HTTP (runs on core 0 only) ----------------
static WiFiClient plainClient;
#if defined(ROOT_CA_PEM)
static WiFiClientSecure tlsClient;
#endif

static bool httpCall(bool post, const char* path, const char* body, int& status, String& payload) {
  status = 0;
  const String url = String(SERVER_BASE) + path;
  HTTPClient http;
  bool begun;
  if (url.startsWith("https://")) {
#if defined(ROOT_CA_PEM)
    tlsClient.setCACert(ROOT_CA_PEM);
    begun = http.begin(tlsClient, url);
#else
    Serial.println("[NET] https:// SERVER_BASE needs ROOT_CA_PEM in config.h (certificate checks are never skipped)");
    return false;
#endif
  } else {
    begun = http.begin(plainClient, url);
  }
  if (!begun) return false;
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.setConnectTimeout(HTTP_TIMEOUT_MS);
  http.addHeader("X-Device-Key", DEVICE_KEY);
  if (post) http.addHeader("Content-Type", "application/json");
  status = post ? http.POST((uint8_t*)body, strlen(body)) : http.GET();
  payload = status > 0 ? http.getString() : "";
  http.end();
  lastStatus = status;
  if (status == 401) keyRejected = true;
  else if (status > 0) keyRejected = false;
  return status > 0;
}

static bool postJson(const char* path, const char* body, int expect) {
  int st = 0;
  String resp;
  const bool ok = httpCall(true, path, body, st, resp) && st == expect;
  if (!ok) Serial.printf("[NET] POST %s -> %d %s\n", path, st, resp.c_str());
  return ok;
}

static bool sendTelemetry() {
  Shared s;
  xSemaphoreTake(sharedMtx, portMAX_DELAY);
  s = shared;
  xSemaphoreGive(sharedMtx);
  if (!s.valid) return true;  // nothing trustworthy to send; do not report this as a network failure
  char body[160];
  snprintf(body, sizeof(body), "{\"voltage\":%.3f,\"current\":%.4f,\"power\":%.4f,\"relay_state\":\"%s\",\"uptime_s\":%lu}",
           s.v, s.i, s.v * s.i, relayWord(s.relayEnergised), (unsigned long)(millis() / 1000));
  return postJson("/api/device/telemetry", body, 202);
}

static bool sendHeartbeat() {
  char body[160];
  snprintf(body, sizeof(body), "{\"firmware_version\":\"%s\",\"wifi_rssi\":%d,\"ip_address\":\"%s\",\"uptime_s\":%lu}",
           FIRMWARE_VERSION, WiFi.RSSI(), WiFi.localIP().toString().c_str(), (unsigned long)(millis() / 1000));
  return postJson("/api/device/heartbeat", body, 202);
}

static bool sendEvent(const EventMsg& e) {
  const char* t = e.type == EV_BOOT ? "BOOT" : e.type == EV_BTN_TRIP ? "PUSHBUTTON_TRIP" : "PUSHBUTTON_RESTORE";
  char body[96];
  snprintf(body, sizeof(body), "{\"type\":\"%s\",\"relay_state\":\"%s\"}", t, relayWord(e.energised));
  return postJson("/api/device/events", body, 202);
}

static bool sendAck(const AckMsg& a) {
  char path[64], body[96];
  snprintf(path, sizeof(path), "/api/device/commands/%lu/ack", (unsigned long)a.id);
  snprintf(body, sizeof(body), "{\"success\":%s,\"relay_state\":\"%s\"}", a.success ? "true" : "false", relayWord(a.energised));
  return postJson(path, body, 200);
}

// A 4xx (other than 408/429) will never succeed on retry, e.g. an ack for a command the server already timed out.
static bool permanentFailure() { return lastStatus >= 400 && lastStatus < 500 && lastStatus != 408 && lastStatus != 429; }

static bool pollCommand() {
  int st = 0;
  String resp;
  if (!httpCall(false, "/api/device/commands/next", nullptr, st, resp)) return false;
  if (st == 204) return true;  // nothing queued
  if (st != 200) return false;
  JsonDocument doc;
  if (deserializeJson(doc, resp) != DeserializationError::Ok) return false;
  const char* action = doc["action"] | "";
  const uint32_t id = doc["id"] | 0;
  if (id == 0 || (strcmp(action, "TRIP") != 0 && strcmp(action, "RESTORE") != 0)) return false;  // ignore anything unexpected
  CmdMsg m{id, strcmp(action, "TRIP") == 0};
  xQueueSend(cmdQ, &m, 0);
  Serial.printf("[CMD] #%lu %s received\n", (unsigned long)id, action);
  return true;
}

static void networkTask(void*) {
  uint32_t lastTel = 0, lastHb = 0, lastCmd = 0, lastOk = 0, lastWifiTry = 0;
  for (;;) {
    const uint32_t now = millis();
    if (WiFi.status() != WL_CONNECTED) {
      netOk = false;
      if (now - lastWifiTry > 10000) { lastWifiTry = now; WiFi.disconnect(); WiFi.begin(WIFI_SSID, WIFI_PASSWORD); }
      vTaskDelay(pdMS_TO_TICKS(500));
      continue;
    }
    bool ok = true;

    EventMsg ev;  // buttons first: they already happened locally
    while (xQueuePeek(eventQ, &ev, 0) == pdTRUE) {
      if (!sendEvent(ev)) {
        ok = false;
        if (permanentFailure()) { xQueueReceive(eventQ, &ev, 0); Serial.println("[NET] event rejected by server; dropped"); continue; }
        break;  // transient: keep it queued and retry next pass
      }
      xQueueReceive(eventQ, &ev, 0);
    }
    AckMsg ack;  // then acknowledgements, so the server stops waiting
    while (xQueuePeek(ackQ, &ack, 0) == pdTRUE) {
      if (!sendAck(ack)) {
        ok = false;
        if (permanentFailure()) { xQueueReceive(ackQ, &ack, 0); Serial.println("[NET] ack rejected by server; dropped"); continue; }
        break;
      }
      xQueueReceive(ackQ, &ack, 0);
    }
    if (now - lastCmd >= COMMAND_POLL_MS)    { lastCmd = now; ok &= pollCommand(); }
    if (now - lastTel >= TELEMETRY_MS)       { lastTel = now; ok &= sendTelemetry(); }
    if (now - lastHb  >= HEARTBEAT_MS)       { lastHb = now;  ok &= sendHeartbeat(); }

    if (ok) lastOk = millis();
    netOk = (millis() - lastOk) < 10000;
    vTaskDelay(pdMS_TO_TICKS(50));
  }
}

// ---------------- pushbutton (report sections 3.8, 5.3) ----------------
static void handleButton() {
  static bool stable = false, lastRaw = false;
  static uint32_t changedAt = 0, pressedAt = 0;
  const bool raw = digitalRead(PIN_BTN) == LOW;  // pressed = LOW
  const uint32_t now = millis();
  if (raw != lastRaw) { lastRaw = raw; changedAt = now; }
  if (raw != stable && now - changedAt >= DEBOUNCE_MS) {
    stable = raw;
    if (stable) {
      pressedAt = now;
    } else {
      const uint32_t held = now - pressedAt;
      if (state == NORMAL) setState(TRIPPED, true);                         // any press+release trips
      else if (held >= RESTORE_HOLD_MS) setState(NORMAL, true);             // restore needs a 3 s hold
      else Serial.println("[BTN] hold >= 3 s to restore");
    }
  }
}

// ---------------- remote commands, executed here (core 1) so only loop() ever drives the relay ----------------
static void handleRemoteCommands() {
  CmdMsg c;
  while (xQueueReceive(cmdQ, &c, 0) == pdTRUE) {
    setState(c.trip ? TRIPPED : NORMAL, false);
    AckMsg a{c.id, true, state == NORMAL};  // report the state actually being driven, after driving it
    xQueueSend(ackQ, &a, 0);
  }
}

// ---------------- setup / loop ----------------
void setup() {
  Serial.begin(115200);
  // Set the level BEFORE switching to OUTPUT so the active-LOW relay does not glitch at boot.
  digitalWrite(PIN_RELAY, LOW);   // start NORMAL: relay energised (report section 5.3)
  digitalWrite(PIN_RED, LOW);
  pinMode(PIN_RELAY, OUTPUT);
  pinMode(PIN_RED, OUTPUT);
  pinMode(PIN_BTN, INPUT_PULLUP);
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_V, ADC_11db);  // full 0-3.3 V range
  analogSetPinAttenuation(PIN_I, ADC_11db);

  sharedMtx = xSemaphoreCreateMutex();
  cmdQ = xQueueCreate(4, sizeof(CmdMsg));
  ackQ = xQueueCreate(8, sizeof(AckMsg));
  eventQ = xQueueCreate(8, sizeof(EventMsg));

  Wire.begin(21, 22);
  lcd.init();
  lcd.backlight();
  lcdLine(0, "Grid Monitor");
  lcdLine(1, "v" FIRMWARE_VERSION);
  applyOutputs();

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  queueEvent(EV_BOOT);  // tells the server the true relay state after every (re)boot
  xTaskCreatePinnedToCore(networkTask, "net", 8192, nullptr, 1, nullptr, 0);
  delay(1200);
  Serial.println("Grid monitoring firmware " FIRMWARE_VERSION " started");
}

void loop() {
  static uint32_t lastSample = 0, lastPage = 0;
  static uint8_t page = 0;
  const uint32_t now = millis();

  handleButton();
  handleRemoteCommands();

  if (now - lastSample >= SAMPLE_MS) {
    lastSample = now;
    measure();
    updateLcd(page);
  }
  if (now - lastPage >= LCD_PAGE_MS) {
    lastPage = now;
    page = (page + 1) % 3;
    updateLcd(page);
  }
  delay(5);
}
