import { useState } from 'react';
import { Loader2, ShieldAlert } from 'lucide-react';
import type { CommandAction } from '../../types';
import { issueCommand, useEngine } from '../../api/store';
import { useAuth } from '../../context/AuthContext';
import ConfirmDialog from '../common/ConfirmDialog';
import StatusBadge from '../common/StatusBadge';

/** One big switch for the single-channel relay. It always shows the state the ESP32 REPORTED, never the click. */
export default function RelayToggle() {
  const { feeder: f, commands } = useEngine();
  const { user } = useAuth();
  const [confirm, setConfirm] = useState<CommandAction | null>(null);
  const [error, setError] = useState<string | null>(null);

  const inFlight = commands.find((c) => c.status === 'PENDING' || c.status === 'SENT');
  const last = commands[0];
  const on = f.relay === 'ENERGISED';
  const offline = !f.installed || f.state === 'OFFLINE';
  const canOperate = user?.role === 'admin' || user?.role === 'operator';
  const disabled = !canOperate || offline || !!inFlight;
  const action: CommandAction = on ? 'TRIP' : 'RESTORE';

  const submit = async () => {
    setConfirm(null);
    const res = await issueCommand(f.id, action, user?.operatorId ?? 'unknown');
    setError(res.ok ? null : res.reason ?? 'Command rejected.');
  };

  return (
    <section className="card p-5">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-navy-900">Relay Control</h3>
        <StatusBadge tone={offline ? 'grey' : on ? 'green' : 'red'}>{offline ? 'Unknown' : on ? 'Energised' : 'Released'}</StatusBadge>
      </div>
      <p className="text-xs text-slate-500">Single-channel relay via ESP32 (GPIO 25)</p>

      <button
        role="switch" aria-checked={on} aria-label="Relay on or off" disabled={disabled} onClick={() => setConfirm(action)}
        className={`relative mx-auto mt-5 block h-20 w-40 rounded-full p-2 shadow-inner transition disabled:opacity-50 ${on ? 'bg-emerald-500' : 'bg-slate-300'}`}
      >
        <span className={`flex h-16 w-16 items-center justify-center rounded-full bg-white text-xs font-bold text-slate-700 shadow-lg transition-transform ${on ? 'translate-x-20' : ''}`}>
          {inFlight ? <Loader2 className="animate-spin" size={22} /> : on ? 'ON' : 'OFF'}
        </span>
      </button>
      <p className="mt-3 text-center text-sm text-slate-600">Load: <b className="capitalize">{f.load.toLowerCase()}</b> · tap to {on ? 'trip' : 'restore'}</p>

      {!canOperate && <p className="mt-3 text-center text-xs text-slate-500">Your role is read-only.</p>}
      {offline && <p className="mt-3 flex items-center justify-center gap-1.5 text-xs text-amber-700"><ShieldAlert size={14} /> Device offline — commands cannot be sent.</p>}
      {error && <p role="alert" className="mt-3 rounded-xl bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>}
      {inFlight && (
        <p role="status" className="mt-3 rounded-xl bg-blue-50 px-3 py-2 text-xs font-medium text-blue-800">
          {inFlight.action} {inFlight.status === 'PENDING' ? 'queued' : 'sent'} — awaiting ESP32 acknowledgement. The switch moves only after the device confirms.
        </p>
      )}
      {!inFlight && last?.status === 'ACKED' && (
        <p role="status" className="mt-3 rounded-xl bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-800">
          {last.action} acknowledged by ESP32 {last.simulatedAck && <StatusBadge tone="blue">SIMULATED ACK</StatusBadge>}
        </p>
      )}
      {!inFlight && last?.status === 'TIMEOUT' && (
        <p role="alert" className="mt-3 rounded-xl bg-red-50 px-3 py-2 text-xs font-medium text-red-800">{last.action} NOT acknowledged. The relay may not have operated — verify on site.</p>
      )}

      <ConfirmDialog
        open={confirm !== null}
        title={confirm === 'TRIP' ? 'Switch relay OFF (trip)?' : 'Switch relay ON (restore)?'}
        confirmLabel={confirm === 'TRIP' ? 'Send Trip command' : 'Send Restore command'}
        tone={confirm === 'TRIP' ? 'danger' : 'success'}
        onConfirm={submit}
        onCancel={() => setConfirm(null)}
      >
        <p>{confirm === 'TRIP' ? 'This asks the ESP32 to release the relay and disconnect the load.' : 'This asks the ESP32 to energise the relay and reconnect the load.'}</p>
        <p>Success is shown only after the ESP32 acknowledges the command.</p>
      </ConfirmDialog>
    </section>
  );
}
