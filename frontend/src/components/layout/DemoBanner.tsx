import { FlaskConical } from 'lucide-react';

export default function DemoBanner() {
  return (
    <div className="flex items-center justify-center gap-2 bg-amber-400 px-4 py-1.5 text-center text-xs font-bold tracking-wide text-amber-950" role="status">
      <FlaskConical size={14} className="shrink-0" />
      DEMO MODE — SIMULATED DATA, NOT LIVE HARDWARE MEASUREMENTS
    </div>
  );
}
