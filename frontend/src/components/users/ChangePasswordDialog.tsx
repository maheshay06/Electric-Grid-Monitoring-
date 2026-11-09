import { useState, type FormEvent } from 'react';
import { Loader2 } from 'lucide-react';
import Modal from '../common/Modal';
import { changeOwnPassword, PASSWORD_HINT } from '../../api/users';

export default function ChangePasswordDialog({ onClose }: { onClose: () => void }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [again, setAgain] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (next !== again) { setErr('The new passwords do not match'); return; }
    setBusy(true);
    try {
      await changeOwnPassword(current, next);
      setDone(true);
      setErr(null);
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : 'Failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Change password" onClose={onClose}>
      {done ? (
        <div>
          <p role="status" className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">Password changed. Your other sessions were signed out.</p>
          <button className="btn-primary mt-4 w-full" onClick={onClose}>Close</button>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-3">
          {([['Current password', current, setCurrent, 'current-password'], ['New password', next, setNext, 'new-password'], ['Repeat new password', again, setAgain, 'new-password']] as const).map(([label, v, set, ac]) => (
            <div key={label}>
              <label className="mb-1 block text-xs font-semibold text-slate-600">{label}</label>
              <input className="input" type="password" value={v} onChange={(e) => set(e.target.value)} autoComplete={ac} required />
            </div>
          ))}
          <p className="text-xs text-slate-500">{PASSWORD_HINT}</p>
          {err && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{err}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
            <button className="btn-primary" disabled={busy}>{busy && <Loader2 size={15} className="animate-spin" />} Change password</button>
          </div>
        </form>
      )}
    </Modal>
  );
}
