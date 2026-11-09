import { Download } from 'lucide-react';
import { useEngine } from '../api/store';
import PageHeader from '../components/common/PageHeader';
import FaultLogTable from '../components/faults/FaultLogTable';
import { downloadCsv, fmtDateTime } from '../utils/format';

export default function FaultHistoryPage() {
  const { faults, demo } = useEngine();
  const exportCsv = () =>
    downloadCsv('fault_events.csv', [
      ['event_id', 'type', 'severity', 'voltage_V', 'current_A', 'timestamp', 'source', 'status', 'simulated'],
      ...faults.map((e) => [e.id, e.type, e.severity, e.voltage.toFixed(3), e.current.toFixed(3), fmtDateTime(e.ts), e.source, e.status, e.simulated ? 'yes' : 'no']),
    ]);
  return (
    <>
      <PageHeader title="Fault History" subtitle="Complete event log with search, sorting and filtering">
        <button className="btn-ghost" onClick={exportCsv} disabled={faults.length === 0}><Download size={15} /> Export CSV</button>
      </PageHeader>
      {demo && <p className="mb-3 text-xs font-semibold text-amber-800">All events below are SIMULATED.</p>}
      <FaultLogTable events={faults} pageSize={12} title="All events" />
    </>
  );
}
