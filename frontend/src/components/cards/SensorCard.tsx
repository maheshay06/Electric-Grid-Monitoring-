import type { LucideIcon } from 'lucide-react';

interface Props {
  label: string;
  hardware: string; // the physical part this reading comes from
  value: string;
  unit: string;
  icon: LucideIcon;
  fraction: number; // 0..1 bar fill (value relative to its safe maximum)
  bad?: boolean;
  limit: string;
  simulated?: boolean;
}

export default function SensorCard({ label, hardware, value, unit, icon: Icon, fraction, bad, limit, simulated }: Props) {
  const bar = bad ? 'bg-red-500' : 'bg-gradient-to-r from-brand to-accent';
  return (
    <div className="card relative p-5">
      {simulated && <span className="absolute right-4 top-4 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-800">SIM</span>}
      <div className="flex items-center gap-3">
        <div className="rounded-2xl bg-brand-light p-3 text-brand-dark"><Icon size={22} /></div>
        <div className="leading-tight">
          <p className="font-semibold text-navy-900">{label}</p>
          <p className="text-xs text-slate-500">{hardware}</p>
        </div>
      </div>
      <p className="mt-4 font-mono text-4xl font-semibold tracking-tight text-navy-900">
        {value}<span className="ml-1.5 text-lg font-medium text-slate-400">{unit}</span>
      </p>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-label={label} aria-valuenow={Math.round(fraction * 100)}>
        <div className={`h-full rounded-full transition-all ${bar}`} style={{ width: `${Math.min(100, Math.max(0, fraction * 100))}%` }} />
      </div>
      <p className="mt-2 text-xs text-slate-500">{limit}</p>
    </div>
  );
}
