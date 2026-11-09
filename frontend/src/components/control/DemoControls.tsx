import { FlaskConical } from 'lucide-react';
import { injectScenario, setDropAck, simulatePushbutton, type Scenario } from '../../api/store';

const SCENARIOS: { key: Scenario; label: string }[] = [
  { key: 'UNDERVOLTAGE', label: 'Undervoltage' },
  { key: 'OVERVOLTAGE', label: 'Overvoltage' },
  { key: 'OVERCURRENT', label: 'Overcurrent' },
  { key: 'ABNORMAL', label: 'Abnormal pattern' },
];

export default function DemoControls({ dropAck }: { dropAck: boolean }) {
  return (
    <section className="card border-amber-300 bg-amber-50/40 p-5">
      <h3 className="flex items-center gap-2 text-sm font-bold text-amber-900"><FlaskConical size={16} /> Demo Controls (simulation only)</h3>
      <p className="mt-1 text-xs text-amber-900/80">Injects synthetic conditions on the feeder for 15 s. Nothing here touches hardware.</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {SCENARIOS.map((s) => (
          <button key={s.key} className="btn-ghost px-4 text-xs" onClick={() => injectScenario(1, s.key)}>{s.label}</button>
        ))}
        <button className="btn-ghost px-4 text-xs" onClick={() => injectScenario(1, null)}>Clear</button>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-4 text-xs">
        <button className="btn-ghost px-4 text-xs" onClick={() => simulatePushbutton(1)}>Simulate pushbutton press</button>
        <label className="flex items-center gap-2 font-medium text-slate-700">
          <input type="checkbox" checked={dropAck} onChange={(e) => setDropAck(e.target.checked)} />
          Simulate ESP32 not acknowledging (timeout)
        </label>
      </div>
    </section>
  );
}
