import type { User } from '../types';
import { api, setToken } from './http';

interface LoginResponse {
  access_token: string;
  user: { operator_id: string; full_name: string; role: User['role']; location_code: string };
}

const toUser = (u: LoginResponse['user']): User => ({
  operatorId: u.operator_id, name: u.full_name, role: u.role, locationId: u.location_code,
});

/** Credentials are validated by the backend (bcrypt hash, location check, lockout). */
export async function login(operatorId: string, password: string, locationId: string): Promise<User> {
  const r = await api<LoginResponse>('/api/auth/login', {
    method: 'POST',
    body: { operator_id: operatorId.trim(), password, location_id: locationId.trim() },
  });
  setToken(r.access_token);
  return toUser(r.user);
}

export async function logout(): Promise<void> {
  try { await api('/api/auth/logout', { method: 'POST' }); } catch { /* token may already be invalid */ }
  setToken(null);
}
