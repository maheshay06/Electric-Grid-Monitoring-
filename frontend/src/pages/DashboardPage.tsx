import { useState } from 'react';
import { Activity, Gauge, Zap } from 'lucide-react';
import { useEngine } from '../api/store';
import type { RangeKey } from '../types';
import RangeSelector from '../components/common/RangeSelector';
import StatusBadge from '../components/common/StatusBadge';
import SensorCard from '../components/cards/SensorCard';
import RelayToggle from '../components/control/RelayToggle';
import MlHealthCard from '../components/ai/MlHealthCard';
import SmsAlertCard from '../components/alerts/SmsAlertCard';
import { CurrentChart, VoltageChart } from '../components/charts/ParameterCharts';
import FaultLogTable from '../components/faults/FaultLogTable';
import { fmt, timeAgo } from '../utils/format';

export default function DashboardPage() {
  const { feeder: f, faults, thresholds: t, demo } = useEngine();
  const [range, setRange] = useState<RangeKey>('5m');
  const live = f.installed && f.state !== 'OFFLINE';
  const grid = !live ? { tone: 'grey' as const, text: 'NO DATA' }
    : f.state === 'TRIPPED' ? { tone: 'red' as const, text: 'TRIPPED' }
    : f.health === 'FAULT' ? { tone: 'amber' as const, text: 'FAULT CONDITION' }
    : { tone: 'green' as const, text: 'NORMAL' };
  const vBad = live && (f.voltage < t.undervoltage || f.voltage > t.overvoltage);
  const iBad = live && f.current > t.overcurrent;

  return (
    <div className="space-y-5">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-navy-900 via-navy-700 to-brand p-6 text-white shadow-card sm:p-8">
        <div className="absolute -right-10 -top-10 h-48 w-48 rounded-full bg-accent/30 blur-3xl" aria-hidden />
        <div className="relative flex flex-wrap items-end justify-between gap-4">
          <div className="max-w-2xl">
            <p className="text-xs font-semibold uppercase tracking-widest text-cyan-200">South Substation · Live feeder</p>
            <h1 className="mt-1 text-2xl font-bold leading-tight sm:text-3xl">Electric Grid Monitoring and Control System using ML</h1>
            <p className="mt-2 text-sm text-indigo-100">Relay {f.relay.toLowerCase()} · load {f.load.toLowerCase()} · updated {f.lastUpdate ? timeAgo(f.lastUpdate) : 'never'}</p>
          </div>
          <div className="flex flex-col items-start gap-2 sm:items-end">
            <span className="text-xs font-semibold uppercase tracking-wide text-indigo-200">Grid status</span>
            <span className="scale-125 origin-left sm:origin-right"><StatusBadge tone={grid.tone} pulse={grid.tone === 'red' || grid.tone === 'amber'}>{grid.text}</StatusBadge></span>
          </div>
        </div>
      </section>

      {!demo && !live && (
        <p role="status" className="rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-600">
          <b>No live data.</b> Demo Mode is off and the ESP32 is not reporting. Readings appear as soon as the device connects.
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <SensorCard label="Voltage" hardware="Voltage sensor module · 5 V input" value={live ? fmt(f.voltage) : '—'} unit="V" icon={Zap}
          fraction={f.voltage / 6} bad={vBad} limit={`Nominal ${t.nominal.toFixed(1)} V · safe ${t.undervoltage.toFixed(1)}–${t.overvoltage.toFixed(1)} V`} simulated={f.simulated} />
        <SensorCard label="Current" hardware="ACS712-5A current sensor" value={live ? fmt(f.current, 3) : '—'} unit="A" icon={Activity}
          fraction={f.current / t.overcurrent} bad={iBad} limit={`Overcurrent limit ${t.overcurrent.toFixed(1)} A · low resolution at LED loads`} simulated={f.simulated} />
        <SensorCard label="Active Power" hardware="Calculated P = V × I" value={live ? fmt(f.power) : '—'} unit="W" icon={Gauge}
          fraction={f.power / (6 * t.overcurrent)} limit="Derived from the two sensors" simulated={f.simulated} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <RelayToggle />
        <MlHealthCard />
        <SmsAlertCard />
      </div>

      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-navy-900">Real-time monitoring</h2>
        <RangeSelector value={range} onChange={setRange} />
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <VoltageChart range={range} thresholds={t} />
        <CurrentChart range={range} thresholds={t} />
      </div>

      <FaultLogTable events={faults} pageSize={6} title="Fault log" />
    </div>
  );
}
