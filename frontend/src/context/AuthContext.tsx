import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { User } from '../types';
import { login as apiLogin, logout as apiLogout } from '../api/auth';
import { getToken, setToken, UNAUTHORIZED_EVENT } from '../api/http';
import { startStore, stopStore } from '../api/store';

interface AuthCtx {
  user: User | null;
  login: (operatorId: string, password: string, locationId: string) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthCtx | null>(null);
const KEY = 'gm_user';

const readStored = (): User | null => {
  if (!getToken()) return null; // a stored profile is useless without its token
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as User) : null;
  } catch {
    return null;
  }
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(readStored);

  const login = useCallback(async (operatorId: string, password: string, locationId: string) => {
    const u = await apiLogin(operatorId, password, locationId);
    try { sessionStorage.setItem(KEY, JSON.stringify(u)); } catch { /* storage unavailable */ }
    setUser(u);
  }, []);

  const logout = useCallback(() => {
    void apiLogout();
    try { sessionStorage.removeItem(KEY); } catch { /* storage unavailable */ }
    setToken(null);
    setUser(null);
  }, []);

  // Live data only flows while someone is signed in; an expired/revoked token signs the user out.
  useEffect(() => {
    if (user) startStore(); else stopStore();
  }, [user]);
  useEffect(() => {
    const h = () => { setToken(null); try { sessionStorage.removeItem(KEY); } catch { /* ignore */ } setUser(null); };
    window.addEventListener(UNAUTHORIZED_EVENT, h);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, h);
  }, []);

  const value = useMemo(() => ({ user, login, logout }), [user, login, logout]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error('useAuth must be used inside AuthProvider');
  return c;
}
