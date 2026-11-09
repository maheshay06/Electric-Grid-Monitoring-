import { api, setToken } from './http';

export type Role = 'admin' | 'operator' | 'viewer';

export interface UserRow {
  id: number;
  operator_id: string;
  full_name: string;
  email: string | null;
  role: Role;
  location_code: string;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface NewUser {
  operator_id: string;
  full_name: string;
  email: string;
  role: Role;
  location_code: string;
  password: string;
}

export const listUsers = () => api<UserRow[]>('/api/users');
export const listLocations = () => api<{ code: string; name: string }[]>('/api/users/locations');
export const createUser = (u: NewUser) => api<UserRow>('/api/users', { method: 'POST', body: { ...u, email: u.email.trim() || null } });
export const updateUser = (id: number, patch: Partial<Pick<UserRow, 'full_name' | 'role' | 'is_active' | 'location_code'> & { email: string | null }>) =>
  api<UserRow>(`/api/users/${id}`, { method: 'PATCH', body: patch });
export const resetUserPassword = (id: number, newPassword: string) =>
  api<void>(`/api/users/${id}/reset-password`, { method: 'POST', body: { new_password: newPassword } });

/** Self-service. The server revokes every other token and returns a fresh one so this session carries on. */
export async function changeOwnPassword(current: string, next: string): Promise<void> {
  const r = await api<{ access_token: string }>('/api/auth/change-password', {
    method: 'POST',
    body: { current_password: current, new_password: next },
  });
  setToken(r.access_token);
}

/** 16 random characters from an unambiguous alphabet; always has a letter and a digit. */
export function generatePassword(): string {
  const letters = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ';
  const digits = '23456789';
  const all = letters + digits;
  const buf = new Uint32Array(16);
  crypto.getRandomValues(buf);
  const chars = Array.from(buf, (n) => all[n % all.length]);
  chars[0] = letters[buf[0] % letters.length];
  chars[1] = digits[buf[1] % digits.length];
  return chars.join('');
}

export const PASSWORD_HINT = 'At least 10 characters with a letter and a digit; must not contain the operator ID.';
