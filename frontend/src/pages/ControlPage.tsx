import { useEngine } from '../api/store';
import PageHeader from '../components/common/PageHeader';
import RelayToggle from '../components/control/RelayToggle';
import CommandHistory from '../components/control/CommandHistory';
import DemoControls from '../components/control/DemoControls';
import FaultLogTable from '../components/faults/FaultLogTable';

export default function ControlPage() {
  const { commands, faults, demo, dropAck } = useEngine();
  return (
    <>
      <PageHeader title="Relay Control" subtitle="Remote trip / restore through the ESP32, with command history" />
      <div className="mx-auto max-w-md"><RelayToggle /></div>
      {demo && <div className="mt-4"><DemoControls dropAck={dropAck} /></div>}
      <div className="mt-4 space-y-4">
        <CommandHistory commands={commands} />
        <FaultLogTable events={faults} pageSize={5} title="Feeder events" />
      </div>
    </>
  );
}
