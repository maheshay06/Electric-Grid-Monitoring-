import { useState } from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import Navbar from '../components/layout/Navbar';
import Sidebar, { BottomNav } from '../components/layout/Sidebar';
import DemoBanner from '../components/layout/DemoBanner';
import { useAuth } from '../context/AuthContext';
import { useEngine } from '../api/store';

export default function AppLayout() {
  const { user } = useAuth();
  const { demo, loaded, error } = useEngine();
  const [open, setOpen] = useState(false);
  if (!user) return <Navigate to="/login" replace />;
  if (!loaded) {
    return (
      <div className="flex h-screen items-center justify-center bg-surface p-6 text-center">
        {error ? (
          <div className="card max-w-md p-6">
            <p className="font-bold text-red-700">Cannot reach the backend</p>
            <p className="mt-1 text-sm text-slate-600">{error}. Start the API (uvicorn) and reload; retrying automatically.</p>
          </div>
        ) : <p className="text-sm text-slate-500">Loading live data…</p>}
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar open={open} onClose={() => setOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        {demo && <DemoBanner />}
        <Navbar onMenu={() => setOpen(true)} />
        <main className="flex-1 overflow-y-auto p-4 pb-20 lg:p-6 lg:pb-6">
          <Outlet />
        </main>
        <BottomNav />
      </div>
    </div>
  );
}
