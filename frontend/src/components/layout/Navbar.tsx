import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bell, ChevronDown, Cpu, KeyRound, LogOut, MapPin, Menu, User as UserIcon } from 'lucide-react';
import { useEngine, markNotificationRead } from '../../api/store';
import { useAuth } from '../../context/AuthContext';
import StatusBadge, { severityTone } from '../common/StatusBadge';
import ChangePasswordDialog from '../users/ChangePasswordDialog';
import { fmtDateTime, timeAgo } from '../../utils/format';

function useClock() {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

function useOutside(ref: React.RefObject<HTMLElement>, close: () => void) {
  useEffect(() => {
    const h = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && close();
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [ref, close]);
}

export default function Navbar({ onMenu }: { onMenu: () => void }) {
  const { demo, feeders, faults, notifications } = useEngine();
  const { user, logout } = useAuth();
  const now = useClock();
  const [bell, setBell] = useState(false);
  const [menu, setMenu] = useState(false);
  const [pwOpen, setPwOpen] = useState(false);
  const bellRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  useOutside(bellRef, () => setBell(false));
  useOutside(menuRef, () => setMenu(false));

  const unread = notifications.filter((n) => !n.read).length;
  const activeFaults = faults.some((f) => f.status === 'ACTIVE');
  const tripped = feeders.some((f) => f.state === 'TRIPPED');
  const dev = feeders.find((f) => f.primary);
  const health = !demo ? { tone: 'grey' as const, text: 'Unknown (no live data)' }
    : activeFaults ? { tone: 'red' as const, text: 'Fault Active' }
    : tripped ? { tone: 'amber' as const, text: 'Attention' }
    : { tone: 'green' as const, text: 'Optimal' };

  return (
    <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-white bg-white/80 px-4 py-2.5 text-navy-900 shadow-sm backdrop-blur">
      <button className="flex h-11 w-11 items-center justify-center rounded-xl hover:bg-slate-100 lg:hidden" onClick={onMenu} aria-label="Open menu"><Menu size={20} /></button>

      <h1 className="hidden max-w-xs truncate text-sm font-bold text-navy-900 xl:block 2xl:max-w-none">Electric Grid Monitoring and Control System using ML</h1>

      <label className="flex min-h-11 items-center gap-2 rounded-xl bg-brand-light px-3 py-1.5 text-sm">
        <MapPin size={15} className="text-brand" />
        <span className="sr-only">Substation</span>
        <select className="bg-transparent text-sm font-medium focus:outline-none" defaultValue="SS-SOUTH" aria-label="Substation">
          <option className="text-slate-900" value="SS-SOUTH">South Substation</option>
        </select>
      </label>

      <div className="hidden items-center gap-2 text-sm md:flex">
        <span className="text-slate-500">System Health:</span>
        <StatusBadge tone={health.tone} pulse={activeFaults}>{health.text}</StatusBadge>
      </div>

      <div className="hidden items-center gap-2 text-sm sm:flex">
        <Cpu size={15} className="text-brand" />
        <span className="text-slate-500">ESP32:</span>
        {demo ? <StatusBadge tone="blue">Simulated</StatusBadge>
          : dev?.state === 'OFFLINE' ? <StatusBadge tone="grey">Disconnected</StatusBadge>
          : <StatusBadge tone="green">Connected</StatusBadge>}
      </div>

      <div className="ml-auto flex items-center gap-3">
        <time className="hidden font-mono text-xs text-slate-500 md:block">{fmtDateTime(now)}</time>

        <div className="relative" ref={bellRef}>
          <button className="relative flex h-11 w-11 items-center justify-center rounded-xl hover:bg-slate-100" onClick={() => setBell((v) => !v)} aria-label={`Notifications, ${unread} unread`}>
            <Bell size={19} />
            {unread > 0 && (
              <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold">{unread > 99 ? '99+' : unread}</span>
            )}
          </button>
          {bell && (
            <div className="card absolute right-0 z-50 mt-2 w-80 max-w-[90vw] overflow-hidden text-slate-800">
              <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
                <span className="text-sm font-bold">Notifications</span>
                <button className="text-xs font-semibold text-brand hover:underline" onClick={() => markNotificationRead()}>Mark all read</button>
              </div>
              <ul className="max-h-80 divide-y divide-slate-100 overflow-y-auto">
                {notifications.slice(0, 8).map((n) => (
                  <li key={n.id} className={`px-4 py-2.5 ${n.read ? '' : 'bg-blue-50/50'}`}>
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-semibold">{n.title}</p>
                      <StatusBadge tone={severityTone(n.severity)}>{n.severity}</StatusBadge>
                    </div>
                    <p className="mt-0.5 text-xs text-slate-500">{n.message}</p>
                    <p className="mt-1 text-[11px] text-slate-400">{timeAgo(n.ts)}</p>
                  </li>
                ))}
                {notifications.length === 0 && <li className="px-4 py-6 text-center text-sm text-slate-500">No notifications</li>}
              </ul>
              <Link to="/alerts" onClick={() => setBell(false)} className="block border-t border-slate-100 px-4 py-2 text-center text-xs font-semibold text-brand hover:bg-slate-50">View all alerts</Link>
            </div>
          )}
        </div>

        <div className="relative" ref={menuRef}>
          <button className="flex min-h-11 items-center gap-2 rounded-xl px-2 py-1.5 hover:bg-slate-100" onClick={() => setMenu((v) => !v)} aria-label="Profile menu">
            <span className="rounded-full bg-brand-light p-1.5 text-brand-dark"><UserIcon size={16} /></span>
            <span className="hidden text-sm font-medium sm:block">{user?.name ?? 'Operator'}</span>
            <ChevronDown size={14} />
          </button>
          {menu && (
            <div className="card absolute right-0 z-50 mt-2 w-56 p-2 text-slate-800">
              <div className="px-3 py-2">
                <p className="text-sm font-semibold">{user?.name}</p>
                <p className="text-xs text-slate-500">ID: {user?.operatorId} · {user?.locationId}</p>
                <p className="text-xs capitalize text-slate-500">Role: {user?.role}</p>
              </div>
              <button className="flex min-h-11 w-full items-center gap-2 rounded-xl px-3 py-2 text-sm hover:bg-slate-100" onClick={() => { setMenu(false); setPwOpen(true); }}><KeyRound size={15} /> Change password</button>
              <button className="flex min-h-11 w-full items-center gap-2 rounded-xl px-3 py-2 text-sm hover:bg-slate-100" onClick={logout}><LogOut size={15} /> Sign out</button>
            </div>
          )}
        </div>
      </div>
      {pwOpen && <ChangePasswordDialog onClose={() => setPwOpen(false)} />}
    </header>
  );
}
