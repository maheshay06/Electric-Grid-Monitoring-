import { useState, type FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { Loader2, Lock, LogIn, MapPin, User, Zap } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function LoginPage() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const [operatorId, setOperatorId] = useState('');
  const [password, setPassword] = useState('');
  const [locationId, setLocationId] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      await login(operatorId, password, locationId);
      nav('/', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed.');
    } finally {
      setBusy(false);
    }
  };

  const field = (id: string, label: string, icon: JSX.Element, value: string, set: (v: string) => void, type = 'text', auto = 'off') => (
    <div>
      <label htmlFor={id} className="mb-1 block text-xs font-semibold text-slate-600">{label}</label>
      <div className="relative">
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">{icon}</span>
        <input id={id} className="input pl-9" type={type} value={value} onChange={(e) => set(e.target.value)} autoComplete={auto} required />
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-navy-950 via-navy-800 to-navy-600 p-4">
      <div className="card grid w-full max-w-4xl overflow-hidden md:grid-cols-2">
        <div className="hidden flex-col justify-between bg-navy-800 p-8 text-white md:flex">
          <div className="w-fit rounded-xl bg-brand p-3"><Zap size={28} /></div>
          <div>
            <h1 className="text-2xl font-bold leading-snug">Electric Grid Monitoring and Control System using ML</h1>
            <p className="mt-3 text-sm text-slate-300">Real-time monitoring, AI-assisted fault classification and acknowledged remote trip/restore.</p>
          </div>
          <p className="text-xs text-slate-400">Low-voltage 5 V DC educational prototype. Not for connection to 240 V AC mains.</p>
        </div>

        <form onSubmit={submit} className="space-y-4 p-8">
          <h2 className="text-center text-xl font-bold text-navy-900">Operator Login</h2>
          {field('op', 'Operator ID / Email', <User size={15} />, operatorId, setOperatorId, 'text', 'username')}
          {field('pw', 'Password', <Lock size={15} />, password, setPassword, 'password', 'current-password')}
          {field('loc', 'Location ID', <MapPin size={15} />, locationId, setLocationId)}
          {error && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
          <button className="btn-primary w-full py-2.5" disabled={busy}>
            {busy ? <Loader2 size={16} className="animate-spin" /> : <LogIn size={16} />} Login
          </button>
          <p className="text-center text-xs text-slate-500">Credentials are validated by the server. Contact your administrator for an account.</p>
        </form>
      </div>
    </div>
  );
}
