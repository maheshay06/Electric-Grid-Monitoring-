import { NavLink } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Activity, Bell, BrainCircuit, Cpu, History, LayoutDashboard, LineChart, Settings, ToggleRight, Users, X, Zap } from 'lucide-react';

export const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/live', label: 'Live Monitoring', icon: Activity },
  { to: '/control', label: 'Relay Control', icon: ToggleRight },
  { to: '/ai', label: 'AI Fault Prediction', icon: BrainCircuit },
  { to: '/faults', label: 'Fault History', icon: History },
  { to: '/analytics', label: 'Analytics', icon: LineChart },
  { to: '/alerts', label: 'Alerts', icon: Bell },
  { to: '/devices', label: 'Device Management', icon: Cpu },
  { to: '/settings', label: 'System Settings', icon: Settings },
  { to: '/users', label: 'User Management', icon: Users, adminOnly: true },
];

/** Pages pinned to the phone/tablet bottom bar. */
const TABS = ['/', '/live', '/control', '/ai', '/alerts'];

const link = ({ isActive }: { isActive: boolean }) =>
  `flex min-h-11 items-center gap-3 rounded-2xl px-4 py-2.5 text-sm font-medium transition ${isActive ? 'bg-gradient-to-r from-brand to-accent text-white shadow-md' : 'text-slate-600 hover:bg-brand-light/60'}`;

export default function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { user } = useAuth();
  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-navy-950/50 lg:hidden" onClick={onClose} />}
      <aside className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-white bg-white/95 backdrop-blur transition-transform lg:static lg:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="flex items-center justify-between gap-3 px-5 py-5">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl bg-gradient-to-br from-brand to-accent p-2.5 text-white shadow-md"><Zap size={22} /></div>
            <p className="text-sm font-bold leading-tight text-navy-900">Electric Grid Monitoring<br />&amp; Control System <span className="text-brand">· ML</span></p>
          </div>
          <button className="flex h-11 w-11 items-center justify-center rounded-xl hover:bg-slate-100 lg:hidden" onClick={onClose} aria-label="Close menu"><X size={18} /></button>
        </div>
        <nav className="flex-1 space-y-1 overflow-y-auto px-3 pb-3" aria-label="Main">
          {NAV.filter((n) => !('adminOnly' in n) || user?.role === 'admin').map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} onClick={onClose} className={link}><Icon size={18} />{label}</NavLink>
          ))}
        </nav>
        <p className="border-t border-slate-100 p-4 text-[11px] leading-snug text-slate-400">Educational 5 V DC prototype. Never connect to 240 V AC mains.</p>
      </aside>
    </>
  );
}

/** Thumb-reach navigation for phones and tablets. */
export function BottomNav() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-5 border-t border-slate-200 bg-white/95 backdrop-blur lg:hidden" aria-label="Quick">
      {NAV.filter((n) => TABS.includes(n.to)).map(({ to, label, icon: Icon, end }) => (
        <NavLink key={to} to={to} end={end} className={({ isActive }) => `flex min-h-14 flex-col items-center justify-center gap-0.5 text-[10px] font-semibold ${isActive ? 'text-brand' : 'text-slate-500'}`}>
          <Icon size={20} />{label.split(' ')[0]}
        </NavLink>
      ))}
    </nav>
  );
}
