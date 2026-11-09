import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Navigate } from 'react-router-dom';
import { KeyRound, UserPlus, Wand2 } from 'lucide-react';
import PageHeader from '../components/common/PageHeader';
import Modal from '../components/common/Modal';
import StatusBadge from '../components/common/StatusBadge';
import { useAuth } from '../context/AuthContext';
import {
  PASSWORD_HINT, createUser, generatePassword, listLocations, listUsers, resetUserPassword, updateUser,
  type NewUser, type Role, type UserRow,
} from '../api/users';
import { fmtDateTime, timeAgo } from '../utils/format';

const ROLE_HELP: Record<Role, string> = {
  admin: 'Everything, including users, thresholds, devices, SMS and Demo Mode',
  operator: 'Acknowledge faults and send Trip / Restore',
  viewer: 'Read-only',
};
const blank = (loc: string): NewUser => ({ operator_id: '', full_name: '', email: '', role: 'operator', location_code: loc, password: '' });

export default function UsersPage() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<UserRow[]>([]);
  const [locs, setLocs] = useState<{ code: string; name: string }[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [adding, setAdding] = useState<NewUser | null>(null);
  const [resetting, setResetting] = useState<UserRow | null>(null);
  const [handover, setHandover] = useState<{ who: string; pw: string } | null>(null);

  const load = useCallback(async () => {
    try { const [u, l] = await Promise.all([listUsers(), listLocations()]); setUsers(u); setLocs(l); setErr(null); }
    catch (e) { setErr(e instanceof Error ? e.message : 'Failed to load users'); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  if (me && me.role !== 'admin') return <Navigate to="/" replace />;

  const act = async (fn: () => Promise<unknown>) => {
    try { await fn(); setErr(null); await load(); } catch (e) { setErr(e instanceof Error ? e.message : 'Failed'); }
  };

  return (
    <>
      <PageHeader title="User Management" subtitle="Accounts, roles and passwords (admin only)">
        <button className="btn-primary" onClick={() => setAdding(blank(locs[0]?.code ?? 'SS-SOUTH'))}><UserPlus size={16} /> Add user</button>
      </PageHeader>

      {err && <p role="alert" className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{err}</p>}
      {handover && (
        <div role="status" className="mb-3 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900">
          Temporary password for <b>{handover.who}</b> (shown once — share it securely and ask them to change it):
          <code className="mt-1 block break-all rounded bg-white p-2 font-mono">{handover.pw}</code>
          <button className="mt-2 text-xs underline" onClick={() => setHandover(null)}>Dismiss</button>
        </div>
      )}

      <section className="card p-4">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-100">
            <thead><tr>{['Operator ID', 'Name', 'Role', 'Location', 'Status', 'Last login', ''].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-slate-100">
              {users.map((u) => {
                const self = u.operator_id === me?.operatorId;
                return (
                  <tr key={u.id} className={u.is_active ? '' : 'opacity-60'}>
                    <td className="td font-mono text-xs font-semibold">{u.operator_id}{self && <span className="ml-1 rounded bg-brand-light px-1 text-[10px] text-brand">YOU</span>}</td>
                    <td className="td">{u.full_name}<span className="block text-xs text-slate-400">{u.email ?? ''}</span></td>
                    <td className="td">
                      <select className="input w-auto py-1 text-xs" value={u.role} disabled={self} aria-label={`Role for ${u.operator_id}`} title={ROLE_HELP[u.role]}
                        onChange={(e) => window.confirm(`Change ${u.operator_id} to ${e.target.value}? They will be signed out everywhere.`) && act(() => updateUser(u.id, { role: e.target.value as Role }))}>
                        {(['admin', 'operator', 'viewer'] as Role[]).map((r) => <option key={r} value={r}>{r}</option>)}
                      </select>
                    </td>
                    <td className="td text-xs">{u.location_code}</td>
                    <td className="td"><StatusBadge tone={u.is_active ? 'green' : 'grey'}>{u.is_active ? 'Active' : 'Deactivated'}</StatusBadge></td>
                    <td className="td whitespace-nowrap text-xs">{u.last_login_at ? <span title={fmtDateTime(new Date(u.last_login_at).getTime())}>{timeAgo(new Date(u.last_login_at).getTime())}</span> : 'never'}</td>
                    <td className="td whitespace-nowrap text-right">
                      <button className="btn-ghost mr-2 px-3 py-1 text-xs" onClick={() => setResetting(u)}><KeyRound size={13} /> Reset password</button>
                      <button className="btn-ghost px-3 py-1 text-xs" disabled={self}
                        onClick={() => window.confirm(u.is_active ? `Deactivate ${u.operator_id}? Their sessions end immediately.` : `Reactivate ${u.operator_id}?`) && act(() => updateUser(u.id, { is_active: !u.is_active }))}>
                        {u.is_active ? 'Deactivate' : 'Reactivate'}
                      </button>
                    </td>
                  </tr>
                );
              })}
              {users.length === 0 && <tr><td colSpan={7} className="td py-6 text-center text-slate-500">No users.</td></tr>}
            </tbody>
          </table>
        </div>
        <ul className="mt-4 space-y-1 text-xs text-slate-500">
          {(Object.keys(ROLE_HELP) as Role[]).map((r) => <li key={r}><b className="text-slate-700">{r}</b>: {ROLE_HELP[r]}</li>)}
          <li>Accounts are deactivated rather than deleted so the audit trail and command history stay intact. You cannot demote or deactivate yourself.</li>
        </ul>
      </section>

      {adding && (
        <Modal title="Add user" onClose={() => setAdding(null)}>
          <form className="space-y-3" onSubmit={(e: FormEvent) => {
            e.preventDefault();
            void act(async () => {
              await createUser(adding);
              setHandover({ who: adding.operator_id, pw: adding.password });
              setAdding(null);
            });
          }}>
            {([['Operator ID', 'operator_id', 'text'], ['Full name', 'full_name', 'text'], ['Email (optional)', 'email', 'email']] as const).map(([label, key, type]) => (
              <div key={key}>
                <label className="mb-1 block text-xs font-semibold text-slate-600">{label}</label>
                <input className="input" type={type} value={adding[key]} onChange={(e) => setAdding({ ...adding, [key]: e.target.value })} required={key !== 'email'} autoComplete="off" />
              </div>
            ))}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-600">Role</label>
                <select className="input" value={adding.role} onChange={(e) => setAdding({ ...adding, role: e.target.value as Role })}>
                  {(['operator', 'viewer', 'admin'] as Role[]).map((r) => <option key={r}>{r}</option>)}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-600">Location</label>
                <select className="input" value={adding.location_code} onChange={(e) => setAdding({ ...adding, location_code: e.target.value })}>
                  {locs.map((l) => <option key={l.code} value={l.code}>{l.code}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold text-slate-600">Temporary password</label>
              <div className="flex gap-2">
                <input className="input font-mono" value={adding.password} onChange={(e) => setAdding({ ...adding, password: e.target.value })} autoComplete="off" required />
                <button type="button" className="btn-ghost px-3" title="Generate" onClick={() => setAdding({ ...adding, password: generatePassword() })}><Wand2 size={15} /></button>
              </div>
              <p className="mt-1 text-xs text-slate-500">{PASSWORD_HINT}</p>
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" className="btn-ghost" onClick={() => setAdding(null)}>Cancel</button>
              <button className="btn-primary">Create user</button>
            </div>
          </form>
        </Modal>
      )}

      {resetting && <ResetDialog user={resetting} onClose={() => setResetting(null)} onDone={(pw) => { setHandover({ who: resetting.operator_id, pw }); setResetting(null); void load(); }} />}
    </>
  );
}

function ResetDialog({ user, onClose, onDone }: { user: UserRow; onClose: () => void; onDone: (pw: string) => void }) {
  const [pw, setPw] = useState(generatePassword());
  const [err, setErr] = useState<string | null>(null);
  return (
    <Modal title={`Reset password: ${user.operator_id}`} onClose={onClose}>
      <form className="space-y-3" onSubmit={async (e) => {
        e.preventDefault();
        try { await resetUserPassword(user.id, pw); onDone(pw); } catch (e2) { setErr(e2 instanceof Error ? e2.message : 'Failed'); }
      }}>
        <p className="text-sm text-slate-600">This signs {user.full_name} out of every session. Share the new password through a secure channel.</p>
        <div className="flex gap-2">
          <input className="input font-mono" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="off" required />
          <button type="button" className="btn-ghost px-3" title="Generate" onClick={() => setPw(generatePassword())}><Wand2 size={15} /></button>
        </div>
        <p className="text-xs text-slate-500">{PASSWORD_HINT}</p>
        {err && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{err}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn-danger">Reset password</button>
        </div>
      </form>
    </Modal>
  );
}
