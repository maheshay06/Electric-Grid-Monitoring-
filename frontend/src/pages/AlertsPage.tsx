import { useState } from 'react';
import { CheckCheck } from 'lucide-react';
import { markNotificationRead, useEngine } from '../api/store';
import PageHeader from '../components/common/PageHeader';
import StatusBadge, { severityTone } from '../components/common/StatusBadge';
import EmptyState from '../components/common/EmptyState';
import SmsPanel from '../components/alerts/SmsPanel';
import { fmtDateTime } from '../utils/format';

export default function AlertsPage() {
  const { notifications } = useEngine();
  const [unreadOnly, setUnreadOnly] = useState(false);
  const list = notifications.filter((n) => !unreadOnly || !n.read);

  return (
    <>
      <PageHeader title="Alerts" subtitle="In-app notifications: voltage / current faults, trips, restores, device connectivity">
        <label className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} /> Unread only</label>
        <button className="btn-ghost" onClick={() => markNotificationRead()}><CheckCheck size={15} /> Mark all read</button>
      </PageHeader>


      {list.length === 0 ? <EmptyState title="No notifications" /> : (
        <ul className="space-y-2">
          {list.map((n) => (
            <li key={n.id} className={`card flex flex-wrap items-start justify-between gap-3 p-4 ${n.read ? 'opacity-70' : 'border-l-4 border-l-brand'}`}>
              <div>
                <div className="flex items-center gap-2">
                  <p className="font-semibold text-navy-900">{n.title}</p>
                  <StatusBadge tone={severityTone(n.severity)}>{n.severity}</StatusBadge>
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">{n.kind.replace('_', ' ')}</span>
                </div>
                <p className="mt-1 text-sm text-slate-600">{n.message}</p>
                <p className="mt-1 text-xs text-slate-400">{fmtDateTime(n.ts)}</p>
              </div>
              {!n.read && <button className="btn-ghost px-3 py-1 text-xs" onClick={() => markNotificationRead(n.id)}>Mark read</button>}
            </li>
          ))}
        </ul>
      )}
      <SmsPanel />
    </>
  );
}
