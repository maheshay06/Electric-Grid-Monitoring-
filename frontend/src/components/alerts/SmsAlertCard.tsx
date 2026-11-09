import { Link } from 'react-router-dom';
import { MessageSquareWarning } from 'lucide-react';
import { useSms } from '../../api/store';
import StatusBadge, { type Tone } from '../common/StatusBadge';
import { timeAgo } from '../../utils/format';

const TONE: Record<string, Tone> = { SENT: 'green', QUEUED: 'blue', FAILED: 'red', SKIPPED: 'grey' };

/** Shows when a Twilio SMS alert was triggered. SENT = accepted by Twilio, not proof of delivery. */
export default function SmsAlertCard() {
  const { status, messages } = useSms(false);
  const recent = messages.filter((m) => m.kind !== 'TEST').slice(0, 4);
  const live = status?.configured && status.enabled;

  return (
    <section className="card p-5">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 font-semibold text-navy-900"><MessageSquareWarning size={18} className="text-brand" /> Twilio SMS Alerts</h3>
        <StatusBadge tone={live ? 'green' : 'grey'}>{live ? 'Armed' : status?.configured ? 'Off' : 'Not configured'}</StatusBadge>
      </div>
      <p className="text-xs text-slate-500">{status ? `${status.active_recipients} recipient(s) · never sent in Demo Mode` : 'Loading…'}</p>

      <ul className="mt-4 space-y-2">
        {recent.map((m) => (
          <li key={m.id} className="flex items-center justify-between gap-2 rounded-2xl bg-slate-50 px-3 py-2.5">
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-navy-900">{m.kind.replace('_', ' ')}</p>
              <p className="text-xs text-slate-500">{m.to} · {timeAgo(new Date(m.created_at).getTime())}</p>
            </div>
            <StatusBadge tone={TONE[m.status] ?? 'grey'}>{m.status}</StatusBadge>
          </li>
        ))}
        {recent.length === 0 && <li className="rounded-2xl bg-slate-50 px-3 py-6 text-center text-sm text-slate-500">No SMS alert triggered yet</li>}
      </ul>
      <Link to="/alerts" className="mt-4 block text-center text-xs font-semibold text-brand hover:underline">Alert log &amp; settings →</Link>
    </section>
  );
}
