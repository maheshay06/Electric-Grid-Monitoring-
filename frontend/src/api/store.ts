/**
 * Live data store: REST for authoritative state, WebSocket as a "something changed" signal.
 *
 * The server never pushes values we trust blindly: every WS message just triggers a re-fetch, and a
 * slow poll keeps the UI correct if the socket drops. Feeder/relay state shown anywhere in the UI is
 * whatever the backend reports (i.e. what the ESP32 reported), never what a button click requested.
 *
 * Single-feeder UI: only feeder 1 (the real hardware) is mapped; the backend's other feeder rows are ignored.
 */
import { useEffect, useState, useSyncExternalStore } from 'react';
import type {
  AppNotification, Command, CommandAction, FaultClass, FaultEvent, Feeder, Health, Prediction, RangeKey,
  Reading, Severity, Thresholds,
} from '../types';
import { api, ApiError, getToken } from './http';

export type Scenario = 'UNDERVOLTAGE' | 'OVERVOLTAGE' | 'OVERCURRENT' | 'ABNORMAL';

interface Snapshot {
  version: number;
  loaded: boolean;
  error: string | null;
  wsConnected: boolean;
  demo: boolean;
  dropAck: boolean;
  feeders: Feeder[]; // always the single prototype feeder
  feeder: Feeder;
  faults: FaultEvent[];
  commands: Command[];
  notifications: AppNotification[];
  predictions: Prediction[]; // newest first
  latestPrediction: Record<number, Prediction | undefined>;
  thresholds: Thresholds;
  scenarios: Record<number, Scenario | null>;
}

const DEFAULT_THRESHOLDS: Thresholds = { nominal: 5.0, undervoltage: 4.5, overvoltage: 5.5, overcurrent: 1.5 };
const NO_FEEDER: Feeder = {
  id: 1, name: 'Feeder', primary: true, installed: false, state: 'OFFLINE', relay: 'UNKNOWN', load: 'UNKNOWN',
  voltage: 0, current: 0, power: 0, health: 'N/A', simulated: false, lastUpdate: null,
};
const empty = (): Snapshot => ({
  version: 0, loaded: false, error: null, wsConnected: false, demo: false, dropAck: false, feeders: [], feeder: NO_FEEDER, faults: [],
  commands: [], notifications: [], predictions: [], latestPrediction: {}, thresholds: DEFAULT_THRESHOLDS, scenarios: {},
});

let S: Snapshot = empty();
const listeners = new Set<() => void>();
const numToDb: Record<number, number> = {};
const dbToNum: Record<number, number> = {};

function emit(patch: Partial<Snapshot> = {}) {
  const next = { ...S, ...patch };
  S = { ...next, feeder: next.feeders[0] ?? NO_FEEDER, version: S.version + 1 };
  listeners.forEach((l) => l());
}

// ------------------------------------------------------------------ raw API shapes + mappers
interface RawFeeder {
  id: number; number: number; name: string; is_installed: boolean; state: string; relay_state: string; load_state: string;
  nominal_voltage: number; uv_threshold: number; ov_threshold: number; oc_threshold: number; simulated: boolean;
  latest: { ts: string; voltage: number; current: number; power: number } | null;
}
interface RawSummary { demo_mode: boolean; feeders: RawFeeder[] }
interface RawFault {
  id: number; feeder_id: number; ts: string; type: string; severity: string; voltage: number | null; current: number | null;
  source: string; status: string; cleared_at: string | null; is_simulated: boolean;
}
interface RawCommand {
  id: number; feeder_id: number; action: string; requested_by_name: string | null; status: string; reason: string | null;
  created_at: string; sent_at: string | null; acked_at: string | null; is_simulated: boolean;
}
interface RawNotification {
  id: number; feeder_id: number | null; kind: string; severity: string; title: string; message: string;
  created_at: string; read_at: string | null;
}
interface RawPrediction {
  feeder_id: number; ts: string; predicted_class: string; confidence: number; severity: string; voltage: number; current: number; power: number;
}

const ms = (iso: string | null | undefined) => (iso ? new Date(iso).getTime() : undefined);
const num = (dbId: number) => dbToNum[dbId] ?? dbId;
const pad = (n: number, w = 4) => String(n).padStart(w, '0');

function mapFeeder(r: RawFeeder, activeFaults: Set<number>): Feeder {
  const state = r.state as Feeder['state'];
  const health: Health =
    !r.is_installed ? 'N/A' : state === 'OFFLINE' ? 'OFFLINE' : state === 'TRIPPED' ? 'WARNING' : activeFaults.has(r.number) ? 'FAULT' : 'OK';
  return {
    id: r.number, name: r.name, primary: r.number === 1, installed: r.is_installed, state,
    relay: r.relay_state as Feeder['relay'], load: r.load_state as Feeder['load'],
    voltage: r.latest?.voltage ?? 0, current: r.latest?.current ?? 0, power: r.latest?.power ?? 0,
    health, simulated: r.simulated, lastUpdate: r.latest && state !== 'OFFLINE' ? ms(r.latest.ts)! : null,
  };
}

const mapFault = (r: RawFault): FaultEvent => ({
  id: `FLT-${pad(r.id)}`, feederId: num(r.feeder_id), ts: ms(r.ts)!, type: r.type as FaultEvent['type'],
  severity: r.severity as Severity, voltage: r.voltage ?? 0, current: r.current ?? 0, source: r.source as FaultEvent['source'],
  status: r.status as FaultEvent['status'], clearedAt: ms(r.cleared_at), simulated: r.is_simulated,
});

const mapCommand = (r: RawCommand): Command => ({
  id: `CMD-${pad(r.id)}`, feederId: num(r.feeder_id), action: r.action as CommandAction, source: 'OPERATOR',
  requestedBy: r.requested_by_name ?? 'unknown', status: r.status as Command['status'], createdAt: ms(r.created_at)!,
  sentAt: ms(r.sent_at), ackedAt: ms(r.acked_at), reason: r.reason ?? undefined, simulatedAck: r.is_simulated,
});

const mapNote = (r: RawNotification): AppNotification => ({
  id: String(r.id), ts: ms(r.created_at)!, kind: r.kind as AppNotification['kind'], severity: r.severity as Severity,
  title: r.title, message: r.message, feederId: r.feeder_id ? num(r.feeder_id) : undefined, read: r.read_at !== null,
});

const mapPrediction = (r: RawPrediction): Prediction => ({
  ts: ms(r.ts)!, feederId: num(r.feeder_id), cls: r.predicted_class as FaultClass, confidence: r.confidence,
  severity: r.severity as Severity, voltage: r.voltage, current: r.current, power: r.power,
});

// ------------------------------------------------------------------ refresh
let running = false;
let queued: 'light' | 'full' | null = null;

async function loadSummary(): Promise<Partial<Snapshot>> {
  const sum = await api<RawSummary>('/api/dashboard/summary');
  sum.feeders = sum.feeders.filter((f) => f.number === 1);
  sum.feeders.forEach((f) => { numToDb[f.number] = f.id; dbToNum[f.id] = f.number; });
  const active = new Set(S.faults.filter((e) => e.status === 'ACTIVE' && e.type !== 'TRIPPED').map((e) => e.feederId));
  const f1 = sum.feeders.find((f) => f.number === 1);
  return {
    demo: sum.demo_mode, loaded: true, error: null,
    feeders: sum.feeders.map((f) => mapFeeder(f, active)),
    thresholds: f1 ? { nominal: f1.nominal_voltage, undervoltage: f1.uv_threshold, overvoltage: f1.ov_threshold, overcurrent: f1.oc_threshold } : S.thresholds,
  };
}

async function loadLatestPredictions(): Promise<Partial<Snapshot>> {
  const nums = Object.keys(numToDb).map(Number);
  const rows = await Promise.all(nums.map((n) => api<RawPrediction | null>(`/api/ai/latest?feeder_id=${numToDb[n]}`).catch(() => null)));
  const latest: Record<number, Prediction | undefined> = {};
  rows.forEach((r, i) => { if (r) latest[nums[i]] = mapPrediction(r); });
  return { latestPrediction: latest };
}

async function refresh(kind: 'light' | 'full') {
  if (running) { queued = queued === 'full' || kind === 'full' ? 'full' : kind; return; }
  running = true;
  try {
    let patch = await loadSummary();
    patch = { ...patch, ...(await loadLatestPredictions()) };
    if (kind === 'full') {
      const demo = patch.demo as boolean;
      const [faults, commands, notes, demoState, ...hist] = await Promise.all([
        api<{ items: RawFault[] }>('/api/faults?limit=500'),
        api<RawCommand[]>('/api/commands?limit=100'),
        api<RawNotification[]>('/api/notifications?limit=200'),
        demo ? api<{ drop_ack: boolean; scenarios: Record<string, Scenario | null> }>('/api/demo/state') : Promise.resolve(null),
        ...Object.keys(numToDb).map((n) => api<RawPrediction[]>(`/api/ai/history?feeder_id=${numToDb[Number(n)]}&limit=60`).catch(() => [])),
      ]);
      const mappedFaults = faults.items.filter((r) => r.feeder_id in dbToNum).map(mapFault);
      const active = new Set(mappedFaults.filter((e) => e.status === 'ACTIVE' && e.type !== 'TRIPPED').map((e) => e.feederId));
      patch = {
        ...patch,
        faults: mappedFaults,
        feeders: (patch.feeders ?? S.feeders).map((f) => ({
          ...f, health: !f.installed ? 'N/A' : f.state === 'OFFLINE' ? 'OFFLINE' : f.state === 'TRIPPED' ? 'WARNING' : active.has(f.id) ? 'FAULT' : 'OK',
        })),
        commands: commands.filter((r) => r.feeder_id in dbToNum).map(mapCommand),
        notifications: notes.filter((r) => r.feeder_id === null || r.feeder_id in dbToNum).map(mapNote),
        predictions: hist.flat().map(mapPrediction).sort((a, b) => b.ts - a.ts),
        dropAck: demoState?.drop_ack ?? false,
        scenarios: Object.fromEntries(Object.entries(demoState?.scenarios ?? {}).map(([k, v]) => [num(Number(k)), v])),
      };
    }
    emit(patch);
  } catch (e) {
    emit({ error: e instanceof Error ? e.message : 'Cannot reach the backend' });
  } finally {
    running = false;
    if (queued) { const k = queued; queued = null; void refresh(k); }
  }
}

// ------------------------------------------------------------------ series cache (charts)
interface SeriesEntry { at: number; data: Reading[]; fetching: boolean }
const series = new Map<string, SeriesEntry>();
const TTL: Record<RangeKey, number> = { '1m': 1500, '5m': 2000, '15m': 3000, '1h': 6000, '24h': 30000 };

async function fetchSeries(key: string, feederNum: number, range: RangeKey) {
  const entry = series.get(key) ?? { at: 0, data: [], fetching: false };
  entry.fetching = true;
  series.set(key, entry);
  try {
    const rows = await api<{ ts: string; voltage: number; current: number; power: number }[]>(
      `/api/readings?feeder_id=${numToDb[feederNum] ?? feederNum}&range=${range}`,
    );
    entry.data = rows.map((r) => ({ ts: ms(r.ts)!, voltage: r.voltage, current: r.current, power: r.power }));
    entry.at = Date.now();
  } catch { /* keep previous data */ } finally {
    entry.fetching = false;
    emit();
  }
}

export function getSeries(feederNum: number, range: RangeKey): Reading[] {
  const key = `${feederNum}:${range}`;
  const e = series.get(key);
  if ((!e || Date.now() - e.at > TTL[range]) && !e?.fetching && S.loaded) queueMicrotask(() => void fetchSeries(key, feederNum, range));
  return e?.data ?? [];
}

// ------------------------------------------------------------------ lifecycle (WebSocket + fallback poll)
let ws: WebSocket | null = null;
let pollLight: ReturnType<typeof setInterval> | null = null;
let pollFull: ReturnType<typeof setInterval> | null = null;
let retry: ReturnType<typeof setTimeout> | null = null;
let attempts = 0;
let active = false;

function connectWs() {
  const token = getToken();
  if (!active || !token) return;
  ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/live`);
  ws.onopen = () => ws?.send(JSON.stringify({ type: 'auth', token })); // token goes in the first message, not the URL
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data as string) as { type: string };
      if (msg.type === 'ready') { attempts = 0; emit({ wsConnected: true }); return; }
      if (msg.type === 'telemetry') void refresh('light');
      else { if (msg.type === 'settings') series.clear(); void refresh('full'); }
    } catch { /* ignore malformed */ }
  };
  ws.onclose = () => {
    emit({ wsConnected: false });
    if (active) retry = setTimeout(connectWs, Math.min(15000, 1000 * 2 ** attempts++));
  };
  ws.onerror = () => ws?.close();
}

export function startStore() {
  if (active) return;
  active = true;
  void refresh('full');
  connectWs();
  pollLight = setInterval(() => void refresh('light'), 5000);
  pollFull = setInterval(() => void refresh('full'), 30000);
}

export function stopStore() {
  active = false;
  [pollLight, pollFull].forEach((t) => t && clearInterval(t));
  if (retry) clearTimeout(retry);
  ws?.close();
  ws = null;
  series.clear();
  S = { ...empty(), version: S.version + 1 };
  listeners.forEach((l) => l());
}

export function useEngine(): Snapshot {
  return useSyncExternalStore((cb) => { listeners.add(cb); return () => { listeners.delete(cb); }; }, () => S);
}

// ------------------------------------------------------------------ actions
const errText = (e: unknown) => (e instanceof ApiError || e instanceof Error ? e.message : 'Request failed');

export async function issueCommand(feederNum: number, action: CommandAction, _requestedBy: string): Promise<{ ok: boolean; reason?: string }> {
  try {
    await api('/api/commands', { method: 'POST', body: { feeder_id: numToDb[feederNum], action } });
    void refresh('full');
    return { ok: true };
  } catch (e) {
    return { ok: false, reason: errText(e) };
  }
}

const demoPost = async (path: string, body: unknown) => { try { await api(path, { method: 'POST', body }); } finally { void refresh('full'); } };
export const injectScenario = (feederNum: number, scenario: Scenario | null, seconds = 15) =>
  demoPost('/api/demo/scenario', { feeder_id: numToDb[feederNum], scenario, seconds });
export const setDropAck = (enabled: boolean) => demoPost('/api/demo/drop-ack', { enabled });
export const simulatePushbutton = (feederNum: number) => demoPost('/api/demo/pushbutton', { feeder_id: numToDb[feederNum] });

export async function setDemoMode(on: boolean): Promise<string | null> {
  try {
    await api('/api/settings', { method: 'PUT', body: { demo_mode: on } });
    series.clear();
    await refresh('full');
    return null;
  } catch (e) { return errText(e); }
}

export async function setThresholds(t: Thresholds): Promise<string | null> {
  try {
    await Promise.all(S.feeders.map((f) => api(`/api/feeders/${numToDb[f.id]}/thresholds`, {
      method: 'PUT',
      body: { nominal_voltage: t.nominal, uv_threshold: t.undervoltage, ov_threshold: t.overvoltage, oc_threshold: t.overcurrent },
    })));
    await refresh('light');
    return null;
  } catch (e) { return errText(e); }
}

export async function markNotificationRead(id?: string) {
  S = { ...S, notifications: S.notifications.map((n) => (!id || n.id === id ? { ...n, read: true } : n)) };
  emit();
  try { await api(id ? `/api/notifications/${id}/read` : '/api/notifications/read-all', { method: 'POST' }); } catch { /* resynced below */ }
  void refresh('full');
}

export async function acknowledgeFault(id: string) {
  try { await api(`/api/faults/${parseInt(id.slice(4), 10)}/acknowledge`, { method: 'POST' }); } finally { void refresh('full'); }
}

// ------------------------------------------------------------------ small data hooks
export interface ModelMetricsData {
  model_available: boolean;
  available: boolean;
  detail?: string;
  algorithm?: string;
  accuracy?: number;
  macro_f1?: number;
  test_samples?: number;
  cv_accuracy_mean?: number;
  per_class?: Record<string, { precision: number; recall: number; f1: number; support: number }>;
  disclaimer?: string;
}

export function useModelMetrics() {
  const [data, setData] = useState<ModelMetricsData | null>(null);
  useEffect(() => { api<ModelMetricsData>('/api/ai/metrics').then(setData).catch(() => setData(null)); }, []);
  return data;
}

export interface DeviceRow {
  id: number; feeder_id: number; name: string; hw_model: string; firmware_version: string | null;
  last_heartbeat_at: string | null; ip_address: string | null; wifi_rssi: number | null; status: string;
}

export function useDevices() {
  const [rows, setRows] = useState<DeviceRow[]>([]);
  useEffect(() => {
    const load = () => api<DeviceRow[]>('/api/devices').then(setRows).catch(() => undefined);
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);
  return rows;
}

export const rotateDeviceKey = (id: number) => api<{ api_key: string }>(`/api/devices/${id}/rotate-key`, { method: 'POST' });

// ------------------------------------------------------------------ SMS (Twilio) admin data
export interface SmsStatus {
  configured: boolean; enabled: boolean; sender: string | null; active_recipients: number;
  repeat_interval_s: number; state_change_interval_s: number;
}
export interface SmsRecipientRow { id: number; phone: string; label: string; is_active: boolean }
export interface SmsMessageRow { id: number; created_at: string; kind: string; to: string; status: string; error: string | null; body: string }

export function useSms(isAdmin: boolean) {
  const [status, setStatus] = useState<SmsStatus | null>(null);
  const [recipients, setRecipients] = useState<SmsRecipientRow[]>([]);
  const [messages, setMessages] = useState<SmsMessageRow[]>([]);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const [s, m, r] = await Promise.all([
          api<SmsStatus>('/api/sms/status'),
          api<SmsMessageRow[]>('/api/sms/messages?limit=30'),
          isAdmin ? api<SmsRecipientRow[]>('/api/sms/recipients') : Promise.resolve([] as SmsRecipientRow[]),
        ]);
        if (alive) { setStatus(s); setMessages(m); setRecipients(r); }
      } catch { /* keep last values */ }
    };
    void load();
    const t = setInterval(load, 8000);
    return () => { alive = false; clearInterval(t); };
  }, [isAdmin, tick]);

  return { status, recipients, messages, reload: async () => setTick((n) => n + 1) };
}

export const smsApi = {
  setEnabled: (enabled: boolean) => api('/api/sms/enabled', { method: 'PUT', body: { enabled } }),
  add: (phone: string, label: string) => api('/api/sms/recipients', { method: 'POST', body: { phone, label } }),
  remove: (id: number) => api(`/api/sms/recipients/${id}`, { method: 'DELETE' }),
  test: (recipientId: number) => api('/api/sms/test', { method: 'POST', body: { recipient_id: recipientId } }),
};
