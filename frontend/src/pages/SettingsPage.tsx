import { useEffect, useState } from 'react';
import { Save } from 'lucide-react';
import { setDemoMode, setThresholds, useEngine } from '../api/store';
import { useAuth } from '../context/AuthContext';
import PageHeader from '../components/common/PageHeader';
import type { Thresholds } from '../types';

const FIELDS: { key: keyof Thresholds; label: string; unit: string; step: number }[] = [
  { key: 'nominal', label: 'Nominal voltage', unit: 'V', step: 0.1 },
  { key: 'undervoltage', label: 'Undervoltage limit (below)', unit: 'V', step: 0.05 },
  { key: 'overvoltage', label: 'Overvoltage limit (above)', unit: 'V', step: 0.05 },
  { key: 'overcurrent', label: 'Overcurrent limit (above)', unit: 'A', step: 0.1 },
];

export default function SettingsPage() {
  const { demo, thresholds } = useEngine();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [draft, setDraft] = useState<Thresholds>(thresholds);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => setDraft(thresholds), [thresholds]);

  const valid = draft.undervoltage < draft.nominal && draft.nominal < draft.overvoltage && draft.overcurrent > 0 && draft.overcurrent <= 5;

  return (
    <>
      <PageHeader title="System Settings" subtitle="Thresholds, calibration notes and demo mode" />

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card p-5">
          <h3 className="text-sm font-bold text-navy-900">Demo Mode</h3>
          <p className="mt-1 text-sm text-slate-600">Generates clearly labelled SIMULATED data when hardware is disconnected. With Demo Mode off and no ESP32, the app shows “no live data” — it never falls back to fake readings.</p>
          <label className="mt-4 flex items-center gap-3 text-sm font-semibold">
            <input type="checkbox" className="h-4 w-4" checked={demo} disabled={!isAdmin} onChange={async (e) => setErr(await setDemoMode(e.target.checked))} />
            Demo Mode {demo ? 'ON' : 'OFF'}
          </label>
          {!isAdmin && <p className="mt-2 text-xs text-slate-500">Admin role required.</p>}
          {demo && <p className="mt-2 text-xs font-semibold text-amber-800">Demo Mode wipes previous simulated data and starts a fresh simulated run. Live readings are never touched.</p>}
        </section>

        <section className="card p-5">
          <h3 className="text-sm font-bold text-navy-900">Fault thresholds</h3>
          <p className="mt-1 text-xs text-slate-500">Defaults suit the 5 V DC prototype. ACS712-5A range is ±5 A.</p>
          <div className="mt-4 space-y-3">
            {FIELDS.map((f) => (
              <label key={f.key} className="flex items-center justify-between gap-3 text-sm">
                <span>{f.label}</span>
                <span className="flex items-center gap-1">
                  <input className="input w-24 text-right" type="number" step={f.step} value={draft[f.key]} disabled={!isAdmin}
                    onChange={(e) => { setSaved(false); setDraft({ ...draft, [f.key]: Number(e.target.value) }); }} />
                  <span className="w-4 text-xs text-slate-400">{f.unit}</span>
                </span>
              </label>
            ))}
          </div>
          {!valid && <p role="alert" className="mt-3 text-xs text-red-600">Require: undervoltage &lt; nominal &lt; overvoltage, and 0 &lt; overcurrent ≤ 5 A.</p>}
          <button className="btn-primary mt-4" disabled={!valid || !isAdmin} onClick={async () => { const e = await setThresholds(draft); setErr(e); setSaved(e === null); }}><Save size={15} /> Save thresholds</button>
          {saved && <span role="status" className="ml-3 text-xs font-semibold text-emerald-700">Saved.</span>}
          {err && <p role="alert" className="mt-2 text-xs text-red-600">{err}</p>}
        </section>

        <section className="card p-5 lg:col-span-2">
          <h3 className="text-sm font-bold text-navy-900">Sensor calibration (reference)</h3>
          <p className="mt-1 text-sm text-slate-600">Calibration constants live in the ESP32 firmware and the device record, and must be measured against a multimeter on real hardware: voltage-module ratio, ACS712 zero-current voltage (≈1.25 V at the pin) and sensitivity (≈92.5 mV/A at the pin). The ACS712-5A resolves roughly 9 mA per ADC count, so very small LED-level currents are unreliable.</p>
        </section>
      </div>
    </>
  );
}
