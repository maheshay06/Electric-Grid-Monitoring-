import { AlertOctagon, CheckCircle2, Info, TriangleAlert } from 'lucide-react';
import type { Prediction } from '../../types';
import StatusBadge, { severityTone } from '../common/StatusBadge';
import { fmt, fmtTime } from '../../utils/format';

export default function PredictionCard({ prediction: p }: { prediction?: Prediction }) {
  if (!p) return null;
  const normal = p.cls === 'NORMAL';
  const Icon = normal ? CheckCircle2 : p.severity === 'High' ? AlertOctagon : TriangleAlert;
  const color = normal ? 'text-emerald-600 bg-emerald-50' : p.severity === 'High' ? 'text-red-600 bg-red-50' : 'text-amber-600 bg-amber-50';
  const pct = Math.round(p.confidence * 100);

  return (
    <section className="card p-5">
      <header className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-navy-900">Latest Prediction</h3>
        <span className="text-xs text-slate-400">{fmtTime(p.ts)}</span>
      </header>

      <div className="mt-4 flex items-center gap-4">
        <div className={`rounded-2xl p-4 ${color}`}><Icon size={34} /></div>
        <div>
          <p className="text-2xl font-bold tracking-tight text-navy-900">{p.cls}</p>
          <div className="mt-1 flex items-center gap-2">
            <StatusBadge tone={severityTone(p.severity)}>Severity: {p.severity}</StatusBadge>
          </div>
        </div>
      </div>

      <div className="mt-5">
        <div className="flex justify-between text-xs font-medium text-slate-500"><span>Confidence</span><span className="font-mono text-slate-800">{pct}%</span></div>
        <div className="mt-1 h-2.5 overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Prediction confidence">
          <div className="h-full rounded-full bg-brand transition-all" style={{ width: `${pct}%` }} />
        </div>
      </div>

      <dl className="mt-5 grid grid-cols-3 gap-2 text-center">
        {[['Voltage', fmt(p.voltage), 'V'], ['Current', fmt(p.current, 3), 'A'], ['Power', fmt(p.power), 'W']].map(([k, v, u]) => (
          <div key={k} className="rounded-lg bg-slate-50 py-2">
            <dt className="text-[11px] text-slate-500">Input · {k}</dt>
            <dd className="font-mono font-semibold">{v} <span className="text-xs text-slate-400">{u}</span></dd>
          </div>
        ))}
      </dl>

      <p className="mt-4 flex gap-2 rounded-lg bg-blue-50 p-3 text-xs text-blue-900">
        <Info size={14} className="mt-0.5 shrink-0" />
        Advisory only. A prediction can never trip or restore a feeder — only a validated operator command can.
      </p>
    </section>
  );
}
