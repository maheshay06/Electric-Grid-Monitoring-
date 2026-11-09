import { useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, Search } from 'lucide-react';
import type { FaultEvent } from '../../types';
import StatusBadge, { severityTone } from '../common/StatusBadge';
import { fmt, fmtDateTime } from '../../utils/format';
import { acknowledgeFault } from '../../api/store';

type SortKey = 'id' | 'type' | 'ts' | 'severity' | 'status';

const SEV_ORDER: Record<string, number> = { None: 0, Low: 1, Medium: 2, High: 3, Critical: 4 };

interface Props {
  events: FaultEvent[];
  pageSize?: number;
  title?: string;
}

export default function FaultLogTable({ events, pageSize = 8, title = 'Fault Log' }: Props) {
  const [q, setQ] = useState('');
  const [type, setType] = useState('ALL');
  const [status, setStatus] = useState('ALL');
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'ts', dir: -1 });
  const [page, setPage] = useState(0);

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const f = events.filter((e) =>
      (type === 'ALL' || e.type === type) &&
      (status === 'ALL' || e.status === status) &&
      (!needle || `${e.id} ${e.type} ${e.source} ${e.status}`.toLowerCase().includes(needle)),
    );
    return [...f].sort((a, b) => {
      const av = sort.key === 'severity' ? SEV_ORDER[a.severity] : a[sort.key];
      const bv = sort.key === 'severity' ? SEV_ORDER[b.severity] : b[sort.key];
      return av < bv ? -sort.dir : av > bv ? sort.dir : 0;
    });
  }, [events, q, type, status, sort]);

  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  const cur = Math.min(page, pages - 1);
  const view = rows.slice(cur * pageSize, cur * pageSize + pageSize);

  const head = (key: SortKey, label: string) => (
    <th className="th" aria-sort={sort.key === key ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
      <button className="inline-flex items-center gap-1 uppercase hover:text-slate-800" onClick={() => setSort((s) => ({ key, dir: s.key === key ? (s.dir === 1 ? -1 : 1) : 1 }))}>
        {label}
        {sort.key === key && (sort.dir === 1 ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}
      </button>
    </th>
  );

  const reset = <T,>(set: (v: T) => void) => (v: T) => { set(v); setPage(0); };

  return (
    <section className="card p-4">
      <header className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-bold text-navy-900">{title} <span className="font-normal text-slate-400">({rows.length})</span></h3>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input className="input w-44 pl-8" placeholder="Search events…" value={q} onChange={(e) => reset(setQ)(e.target.value)} aria-label="Search events" />
          </div>
          <select className="input w-auto" value={type} onChange={(e) => reset(setType)(e.target.value)} aria-label="Filter by type">
            <option value="ALL">All types</option>
            {['UNDERVOLTAGE', 'OVERVOLTAGE', 'OVERCURRENT', 'TRIPPED', 'RESTORED', 'DEVICE_OFFLINE'].map((t) => <option key={t}>{t}</option>)}
          </select>
          <select className="input w-auto" value={status} onChange={(e) => reset(setStatus)(e.target.value)} aria-label="Filter by status">
            <option value="ALL">All status</option>
            {['ACTIVE', 'ACKNOWLEDGED', 'CLEARED'].map((t) => <option key={t}>{t}</option>)}
          </select>
        </div>
      </header>

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-100">
          <thead>
            <tr>
              {head('id', 'Event ID')}{head('type', 'Type')}{head('severity', 'Severity')}
              <th className="th">V / A</th>{head('ts', 'Timestamp')}{head('status', 'Status')}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {view.map((e) => (
              <tr key={e.id} className="hover:bg-slate-50">
                <td className="td font-mono text-xs text-brand">{e.id}{e.simulated && <span className="ml-1 rounded bg-amber-100 px-1 text-[9px] font-bold text-amber-800">SIM</span>}</td>
                <td className="td font-medium">{e.type.replace('_', ' ')}<span className="block text-[11px] font-normal text-slate-400">{e.source}</span></td>
                <td className="td"><StatusBadge tone={severityTone(e.severity)}>{e.severity}</StatusBadge></td>
                <td className="td font-mono text-xs">{fmt(e.voltage)} V / {fmt(e.current, 3)} A</td>
                <td className="td whitespace-nowrap text-xs">{fmtDateTime(e.ts)}</td>
                <td className="td">
                  {e.status === 'ACTIVE' ? (
                    <button className="rounded-full bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-700 ring-1 ring-red-200 hover:bg-red-100" onClick={() => acknowledgeFault(e.id)} title="Click to acknowledge">ACTIVE · Ack</button>
                  ) : (
                    <StatusBadge tone={e.status === 'CLEARED' ? 'green' : 'blue'}>{e.status}</StatusBadge>
                  )}
                </td>
              </tr>
            ))}
            {view.length === 0 && <tr><td className="td py-8 text-center text-slate-500" colSpan={6}>No events match the current filters.</td></tr>}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <footer className="mt-3 flex items-center justify-between text-xs text-slate-500">
          <span>Page {cur + 1} of {pages}</span>
          <div className="flex gap-2">
            <button className="btn-ghost px-3 py-1" disabled={cur === 0} onClick={() => setPage(cur - 1)}>Previous</button>
            <button className="btn-ghost px-3 py-1" disabled={cur >= pages - 1} onClick={() => setPage(cur + 1)}>Next</button>
          </div>
        </footer>
      )}
    </section>
  );
}
