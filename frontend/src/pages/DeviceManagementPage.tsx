import { useState } from 'react';
import { KeyRound } from 'lucide-react';
import { rotateDeviceKey, useDevices, useEngine } from '../api/store';
import { useAuth } from '../context/AuthContext';
import PageHeader from '../components/common/PageHeader';
import StatusBadge from '../components/common/StatusBadge';
import { fmtDateTime, timeAgo } from '../utils/format';

// Pin map taken from the project report (Table 4.2). Do not change without hardware review.
const PINS: [string, string, string][] = [
  ['34', 'Voltage sensor OUT', 'Input only; max 3.3 V'],
  ['35', 'ACS712 OUT via 10 kΩ / 10 kΩ divider', 'Zero ≈ 1.25 V, ≈ 92.5 mV/A at pin'],
  ['25', 'Relay IN', 'Active-LOW (LOW = energised)'],
  ['26', 'Pushbutton to GND', 'INPUT_PULLUP; short = trip, hold ≥ 3 s = restore'],
  ['32', 'Red LED via 330 Ω', 'ON when TRIPPED'],
  ['21 / 22', 'LCD SDA / SCL', 'I2C 0x27, 16×2'],
];

export default function DeviceManagementPage() {
  const { demo } = useEngine();
  const devices = useDevices();
  const { user } = useAuth();
  const [newKey, setNewKey] = useState<{ id: number; key: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const rotate = async (id: number) => {
    if (!window.confirm('Rotate this device key? The ESP32 stops working until it is flashed with the new key.')) return;
    try { setNewKey({ id, key: (await rotateDeviceKey(id)).api_key }); setErr(null); } catch (e) { setErr(e instanceof Error ? e.message : 'Failed'); }
  };

  return (
    <>
      <PageHeader title="Device Management" subtitle="ESP32 connectivity, firmware and hardware configuration" />
      {demo && <p className="mb-3 rounded-lg bg-amber-50 p-3 text-xs font-semibold text-amber-900">Demo Mode is on: the dashboard shows SIMULATED data. The real device status below is unaffected.</p>}

      <section className="card p-4">
        <h3 className="mb-3 text-sm font-bold text-navy-900">Registered devices</h3>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-100">
            <thead><tr>{['Device', 'Status', 'Last heartbeat', 'Firmware', 'Wi-Fi RSSI', 'IP', 'API key'].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
            <tbody>
              {devices.map((d) => (
                <tr key={d.id}>
                  <td className="td font-semibold">{d.name}</td>
                  <td className="td"><StatusBadge tone={d.status === 'ONLINE' ? 'green' : 'grey'}>{d.status === 'ONLINE' ? 'Online' : 'Disconnected'}</StatusBadge></td>
                  <td className="td text-xs">{d.last_heartbeat_at ? `${timeAgo(new Date(d.last_heartbeat_at).getTime())} (${fmtDateTime(new Date(d.last_heartbeat_at).getTime())})` : 'never'}</td>
                  <td className="td text-xs">{d.firmware_version ?? '—'}</td>
                  <td className="td text-xs">{d.wifi_rssi !== null ? `${d.wifi_rssi} dBm` : '—'}</td>
                  <td className="td font-mono text-xs">{d.ip_address ?? '—'}</td>
                  <td className="td"><button className="btn-ghost px-3 py-1 text-xs" disabled={user?.role !== 'admin'} onClick={() => rotate(d.id)}><KeyRound size={13} /> Rotate</button></td>
                </tr>
              ))}
              {devices.length === 0 && <tr><td colSpan={7} className="td py-6 text-center text-slate-500">No devices registered. Run backend/seed.py.</td></tr>}
            </tbody>
          </table>
        </div>
        {err && <p role="alert" className="mt-3 text-xs text-red-600">{err}</p>}
        {newKey && (
          <div role="status" className="mt-3 rounded-lg bg-emerald-50 p-3 text-xs text-emerald-900">
            New key for device {newKey.id} (shown once — copy it into firmware config.h now):
            <code className="mt-1 block break-all rounded bg-white p-2 font-mono">{newKey.key}</code>
            <button className="mt-2 underline" onClick={() => setNewKey(null)}>Dismiss</button>
          </div>
        )}
      </section>

      <section className="card mt-4 p-4">
        <h3 className="mb-3 text-sm font-bold text-navy-900">ESP32 DevKit V1 pin configuration (from project report)</h3>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-100">
            <thead><tr>{['GPIO', 'Function', 'Notes'].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-slate-100">
              {PINS.map(([g, fn, note]) => (
                <tr key={g}><td className="td font-mono font-semibold">{g}</td><td className="td">{fn}</td><td className="td text-slate-500">{note}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-900">Safety: 5 V DC only. Never exceed 3.3 V on GPIO34/35. Relay needs a regulated 5 V supply and common ground. Never connect to 240 V AC.</p>
      </section>
    </>
  );
}
