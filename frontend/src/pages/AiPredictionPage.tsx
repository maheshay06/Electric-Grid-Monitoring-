import { FlaskConical } from 'lucide-react';
import { useEngine } from '../api/store';
import PageHeader from '../components/common/PageHeader';
import EmptyState from '../components/common/EmptyState';
import PredictionCard from '../components/ai/PredictionCard';
import ModelMetrics from '../components/ai/ModelMetrics';
import StatusBadge, { severityTone } from '../components/common/StatusBadge';
import { fmt, fmtTime } from '../utils/format';

export default function AiPredictionPage() {
  const { feeder, latestPrediction, predictions, faults } = useEngine();
  const pred = latestPrediction[feeder.id];
  const ruleActive = faults.filter((e) => e.status === 'ACTIVE').map((e) => e.type);

  return (
    <>
      <PageHeader title="AI Fault Prediction" subtitle="Classifies NORMAL · UNDERVOLTAGE · OVERVOLTAGE · OVERCURRENT · ABNORMAL CONDITION" />

      <div className="mb-4 flex items-start gap-2 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
        <FlaskConical size={16} className="mt-0.5 shrink-0" />
        <span><b>Synthetic demo model.</b> The scikit-learn classifier was trained on generated data, not real measurements. Its output is advisory and can never operate a relay.</span>
      </div>

      {!pred ? (
        <EmptyState title="No prediction available">Predictions need incoming telemetry and a trained model (ml/train_model.py). Enable Demo Mode or connect the ESP32.</EmptyState>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-4">
            <PredictionCard prediction={pred} />
            <section className="card p-5">
              <h3 className="text-sm font-bold text-navy-900">Rule engine vs. AI</h3>
              <p className="mt-2 text-sm text-slate-600">
                Threshold rules (deterministic): {ruleActive.length ? <b className="text-red-700">{ruleActive.join(', ')}</b> : <b className="text-emerald-700">no active fault</b>}
              </p>
              <p className="mt-1 text-sm text-slate-600">AI classification (advisory): <b>{pred.cls}</b></p>
              <p className="mt-2 text-xs text-slate-500">When the two disagree, the operator decides. Neither can operate the relay automatically.</p>
            </section>
          </div>
          <ModelMetrics />
        </div>
      )}

      <section className="card mt-4 p-4">
        <h3 className="mb-3 text-sm font-bold text-navy-900">Prediction History</h3>
        <div className="max-h-80 overflow-auto">
          <table className="min-w-full divide-y divide-slate-100">
            <thead className="sticky top-0 bg-white"><tr>{['Time', 'Class', 'Confidence', 'Severity', 'V', 'A'].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-slate-100">
              {predictions.slice(0, 40).map((p) => (
                <tr key={p.ts}>
                  <td className="td font-mono text-xs">{fmtTime(p.ts)}</td>
                  <td className="td font-medium">{p.cls}</td>
                  <td className="td font-mono text-xs">{Math.round(p.confidence * 100)}%</td>
                  <td className="td"><StatusBadge tone={severityTone(p.severity)}>{p.severity}</StatusBadge></td>
                  <td className="td font-mono text-xs">{fmt(p.voltage)}</td>
                  <td className="td font-mono text-xs">{fmt(p.current, 3)}</td>
                </tr>
              ))}
              {predictions.length === 0 && <tr><td colSpan={6} className="td py-6 text-center text-slate-500">No history yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
