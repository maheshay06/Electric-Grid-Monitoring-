import type { Command } from '../../types';
import StatusBadge, { type Tone } from '../common/StatusBadge';
import { fmtDateTime } from '../../utils/format';

const TONE: Record<string, Tone> = { PENDING: 'grey', SENT: 'blue', ACKED: 'green', FAILED: 'red', TIMEOUT: 'red', REJECTED: 'red' };

export default function CommandHistory({ commands }: { commands: Command[] }) {
  return (
    <section className="card p-4">
      <h3 className="mb-3 text-sm font-bold text-navy-900">Command History</h3>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-100">
          <thead><tr>{['ID', 'Action', 'By', 'Requested', 'Status', 'Acknowledged'].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-slate-100">
            {commands.map((c) => (
              <tr key={c.id}>
                <td className="td font-mono text-xs">{c.id}</td>
                <td className="td font-semibold">{c.action}</td>
                <td className="td">{c.requestedBy}</td>
                <td className="td whitespace-nowrap text-xs">{fmtDateTime(c.createdAt)}</td>
                <td className="td"><StatusBadge tone={TONE[c.status]}>{c.status}</StatusBadge></td>
                <td className="td whitespace-nowrap text-xs">
                  {c.ackedAt ? <>{fmtDateTime(c.ackedAt)} <span className="rounded bg-amber-100 px-1 text-[9px] font-bold text-amber-800">SIM</span></> : c.reason ?? '—'}
                </td>
              </tr>
            ))}
            {commands.length === 0 && <tr><td colSpan={6} className="td py-8 text-center text-slate-500">No commands issued in this session.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}
