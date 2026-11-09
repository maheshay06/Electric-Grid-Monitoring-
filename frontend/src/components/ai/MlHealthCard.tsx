import { Link } from 'react-router-dom';
import { BrainCircuit } from 'lucide-react';
import { useEngine } from '../../api/store';
import { fmtTime } from '../../utils/format';

/** Advisory ML grid-health indicator. It never operates the relay. */
export default function MlHealthCard() {
  const { latestPrediction, feeder: f } = useEngine();
  const p = latestPrediction[f.id];
  const look = !p ? { ring: 'ring-slate-200 bg-slate-50 text-slate-500', word: 'Awaiting data', hint: 'No prediction yet' }
    : p.cls === 'NORMAL' ? { ring: 'ring-emerald-200 bg-emerald-50 text-emerald-700', word: 'Healthy', hint: 'Grid looks normal' }
    : p.severity === 'High' || p.severity === 'Critical' ? { ring: 'ring-red-200 bg-red-50 text-red-700', word: 'Fault likely', hint: p.cls }
    : { ring: 'ring-amber-200 bg-amber-50 text-amber-700', word: 'Warning', hint: p.cls };
  const pct = p ? Math.round(p.confidence * 100) : 0;

  return (
    <section className="card p-5">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 font-semibold text-navy-900"><BrainCircuit size={18} className="text-brand" /> ML Grid Health</h3>
        {p && <span className="text-xs text-slate-400">{fmtTime(p.ts)}</span>}
      </div>
      <p className="text-xs text-slate-500">Random Forest · synthetic training data · advisory only</p>

      <div className={`mt-5 rounded-3xl p-5 text-center ring-1 ring-inset ${look.ring}`}>
        <p className="text-3xl font-bold tracking-tight">{look.word}</p>
        <p className="mt-1 text-sm font-medium">{look.hint}</p>
      </div>

      <div className="mt-4">
        <div className="flex justify-between text-xs font-medium text-slate-500"><span>Confidence</span><span className="font-mono text-slate-800">{p ? `${pct}%` : '—'}</span></div>
        <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-gradient-to-r from-brand to-accent" style={{ width: `${pct}%` }} /></div>
      </div>
      <Link to="/ai" className="mt-4 block text-center text-xs font-semibold text-brand hover:underline">Prediction details →</Link>
    </section>
  );
}
