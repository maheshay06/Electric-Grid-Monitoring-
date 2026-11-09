import type { ReactNode } from 'react';
import { PlugZap } from 'lucide-react';

export default function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center">
      <PlugZap className="text-slate-400" size={28} />
      <p className="font-semibold text-slate-700">{title}</p>
      {children && <p className="max-w-md text-sm text-slate-500">{children}</p>}
    </div>
  );
}
