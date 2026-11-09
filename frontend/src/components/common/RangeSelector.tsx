import type { RangeKey } from '../../types';
import { RANGES } from '../../utils/format';

export default function RangeSelector({ value, onChange }: { value: RangeKey; onChange: (r: RangeKey) => void }) {
  return (
    <div className="inline-flex rounded-lg bg-slate-100 p-0.5" role="tablist" aria-label="Time range">
      {RANGES.map((r) => (
        <button
          key={r.key}
          role="tab"
          aria-selected={value === r.key}
          onClick={() => onChange(r.key)}
          className={`rounded-md px-2.5 py-1 text-xs font-semibold transition ${value === r.key ? 'bg-white text-brand shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
        >
          {r.label}
        </button>
      ))}
    </div>
  );
}
