import { FlaskConical } from 'lucide-react';
import { useModelMetrics } from '../../api/store';

const CLASSES = ['NORMAL', 'UNDERVOLTAGE', 'OVERVOLTAGE', 'OVERCURRENT', 'ABNORMAL CONDITION'];
const pct = (x: number | undefined) => (x === undefined ? '—' : `${(x * 100).toFixed(1)}%`);

/** Figures come from ml/models/metrics.json via GET /api/ai/metrics. Nothing is shown if no model was trained. */
export default function ModelMetrics() {
  const m = useModelMetrics();
  const ok = !!m?.available;
  return (
    <section className="card p-5">
      <h3 className="text-sm font-bold text-navy-900">Model Performance</h3>
      <p className="mt-2 flex gap-2 rounded-lg bg-amber-50 p-3 text-xs font-medium text-amber-900">
        <FlaskConical size={14} className="mt-0.5 shrink-0" />
        Synthetic demo model — trained on generated data, not real measurements. These metrics describe performance on synthetic test data only.
      </p>
      {!ok && <p className="mt-3 text-xs text-slate-500">{m?.detail ?? 'Metrics unavailable. Run ml/generate_dataset.py and ml/train_model.py.'}</p>}
      {ok && <p className="mt-3 text-xs text-slate-500">{m?.algorithm}</p>}
      <div className="mt-2 grid grid-cols-3 gap-2 text-center">
        {[['Accuracy', pct(m?.accuracy)], ['Macro F1', m?.macro_f1 === undefined ? '—' : m.macro_f1.toFixed(3)], ['Test samples', m?.test_samples?.toString() ?? '—']].map(([k, v]) => (
          <div key={k} className="rounded-lg bg-slate-50 py-3">
            <p className={`font-mono text-xl font-semibold ${ok ? 'text-navy-900' : 'text-slate-400'}`}>{v}</p>
            <p className="text-[11px] text-slate-500">{k}</p>
          </div>
        ))}
      </div>
      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full text-xs">
          <thead><tr>{['Class', 'Precision', 'Recall', 'F1'].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-slate-100">
            {CLASSES.map((c) => {
              const r = m?.per_class?.[c];
              return (
                <tr key={c}>
                  <td className="td font-medium">{c}</td>
                  <td className="td">{pct(r?.precision)}</td><td className="td">{pct(r?.recall)}</td><td className="td">{r ? r.f1.toFixed(3) : '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {ok && m?.cv_accuracy_mean !== undefined && <p className="mt-3 text-xs text-slate-500">5-fold cross-validation accuracy: {pct(m.cv_accuracy_mean)} (synthetic data).</p>}
    </section>
  );
}
