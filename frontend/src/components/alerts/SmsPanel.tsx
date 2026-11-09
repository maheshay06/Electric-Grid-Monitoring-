import { useState } from 'react';
import { MessageSquareWarning, Send, Trash2 } from 'lucide-react';
import { smsApi, useSms } from '../../api/store';
import { useAuth } from '../../context/AuthContext';
import StatusBadge, { type Tone } from '../common/StatusBadge';
import { fmtDateTime } from '../../utils/format';

const TONE: Record<string, Tone> = { QUEUED: 'blue', SENT: 'green', FAILED: 'red', SKIPPED: 'grey' };

export default function SmsPanel() {
  const { user } = useAuth();
  const admin = user?.role === 'admin';
  const { status, recipients, messages, reload } = useSms(admin);
  const [phone, setPhone] = useState('');
  const [label, setLabel] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    try { await fn(); setErr(null); setInfo(ok ?? null); await reload(); } catch (e) { setInfo(null); setErr(e instanceof Error ? e.message : 'Failed'); }
  };

  return (
    <section className="card mt-6 p-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-bold text-navy-900"><MessageSquareWarning size={16} /> SMS alerts (Twilio)</h3>
        {status && (
          <div className="flex items-center gap-2">
            <StatusBadge tone={status.configured ? 'green' : 'grey'}>{status.configured ? 'Twilio configured' : 'Not configured'}</StatusBadge>
            <StatusBadge tone={status.enabled ? 'green' : 'grey'}>{status.enabled ? 'Alerts ON' : 'Alerts OFF'}</StatusBadge>
          </div>
        )}
      </header>

      <p className="mt-2 text-xs text-slate-600">
        Texts are sent for faults (under/over-voltage, overcurrent), ESP32-reported trips and restores, controller boot, and lost communication.
        The same fault is texted at most once per {status ? Math.round(status.repeat_interval_s / 60) : 15} min. Messages say what the ESP32 <b>reported</b>; they never claim the contacts physically opened.
        <b> Demo Mode and simulated data never send SMS.</b> “Sent” means Twilio accepted the message, not that a phone received it.
      </p>

      {status && !status.configured && (
        <p className="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-900">
          Add <code>TWILIO_ACCOUNT_SID</code>, <code>TWILIO_AUTH_TOKEN</code> and <code>TWILIO_FROM_NUMBER</code> (or <code>TWILIO_MESSAGING_SERVICE_SID</code>) to <code>backend/.env</code> and restart the API. Tokens are never shown in the app.
        </p>
      )}

      {admin && status && (
        <label className="mt-4 flex items-center gap-3 text-sm font-semibold">
          <input type="checkbox" className="h-4 w-4" checked={status.enabled} disabled={!status.configured}
            onChange={(e) => run(() => smsApi.setEnabled(e.target.checked))} />
          Send SMS alerts {status.sender && <span className="font-normal text-slate-500">from {status.sender}</span>}
        </label>
      )}

      {admin && (
        <div className="mt-4">
          <h4 className="text-xs font-bold uppercase tracking-wide text-slate-500">Recipients</h4>
          <ul className="mt-2 divide-y divide-slate-100">
            {recipients.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                <span><span className="font-mono">{r.phone}</span> <span className="text-slate-500">{r.label}</span></span>
                <span className="flex gap-2">
                  <button className="btn-ghost px-3 py-1 text-xs" disabled={!status?.configured}
                    onClick={() => window.confirm(`Send one REAL test SMS to ${r.phone}? Twilio bills for it.`) && run(() => smsApi.test(r.id), 'Test queued — check the messages table.')}>
                    <Send size={13} /> Send test
                  </button>
                  <button className="btn-ghost px-3 py-1 text-xs" aria-label={`Remove ${r.phone}`}
                    onClick={() => window.confirm(`Remove ${r.phone}?`) && run(() => smsApi.remove(r.id))}><Trash2 size={13} /></button>
                </span>
              </li>
            ))}
            {recipients.length === 0 && <li className="py-3 text-xs text-slate-500">No recipients yet. Use E.164 format, e.g. +919876543210. Twilio trial accounts can only text numbers verified in the Twilio console.</li>}
          </ul>
          <form className="mt-2 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); run(async () => { await smsApi.add(phone, label); setPhone(''); setLabel(''); }); }}>
            <input className="input w-48" placeholder="+919876543210" value={phone} onChange={(e) => setPhone(e.target.value)} aria-label="Phone number" required />
            <input className="input w-40" placeholder="Label (optional)" value={label} onChange={(e) => setLabel(e.target.value)} aria-label="Label" maxLength={60} />
            <button className="btn-primary px-4 py-2 text-xs">Add recipient</button>
          </form>
        </div>
      )}
      {err && <p role="alert" className="mt-3 text-xs text-red-600">{err}</p>}
      {info && <p role="status" className="mt-3 text-xs font-semibold text-emerald-700">{info}</p>}

      <div className="mt-5 overflow-x-auto">
        <h4 className="text-xs font-bold uppercase tracking-wide text-slate-500">Recent messages</h4>
        <table className="mt-2 min-w-full divide-y divide-slate-100">
          <thead><tr>{['Time', 'Event', 'To', 'Status', 'Detail'].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-slate-100">
            {messages.map((m) => (
              <tr key={m.id} title={m.body}>
                <td className="td whitespace-nowrap text-xs">{fmtDateTime(new Date(m.created_at).getTime())}</td>
                <td className="td text-xs font-medium">{m.kind.replace('_', ' ')}</td>
                <td className="td font-mono text-xs">{m.to}</td>
                <td className="td"><StatusBadge tone={TONE[m.status] ?? 'grey'}>{m.status}</StatusBadge></td>
                <td className="td text-xs text-slate-500">{m.error ?? (m.status === 'SENT' ? 'Accepted by Twilio' : '')}</td>
              </tr>
            ))}
            {messages.length === 0 && <tr><td colSpan={5} className="td py-6 text-center text-slate-500">No SMS activity yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}
