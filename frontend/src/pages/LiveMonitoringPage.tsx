import { useState } from 'react';
import { useEngine } from '../api/store';
import type { RangeKey } from '../types';
import PageHeader from '../components/common/PageHeader';
import RangeSelector from '../components/common/RangeSelector';
import EmptyState from '../components/common/EmptyState';
import { CurrentChart, PowerChart, VoltageChart } from '../components/charts/ParameterCharts';
import { fmt, fmtTime } from '../utils/format';

export default function LiveMonitoringPage() {
  const { feeder: f, thresholds } = useEngine();
  const [range, setRange] = useState<RangeKey>('1m');
  const hasData = f.installed && f.state !== 'OFFLINE';

  return (
    <>
      <PageHeader title="Live Monitoring" subtitle="Voltage, current and power vs time">
        <RangeSelector value={range} onChange={setRange} />
      </PageHeader>

      {!hasData ? (
        <EmptyState title="No live data">The ESP32 is not connected. Enable Demo Mode in System Settings to see clearly-labelled simulated data.</EmptyState>
      ) : (
        <>
          <div className="card mb-4 grid grid-cols-2 gap-4 p-5 text-center sm:grid-cols-4">
            {[['Voltage', fmt(f.voltage), 'V'], ['Current', fmt(f.current, 3), 'A'], ['Power', fmt(f.power), 'W']].map(([k, v, u]) => (
              <div key={k}><p className="label">{k}</p><p className="font-mono text-3xl font-semibold text-navy-900">{v}<span className="ml-1 text-base text-slate-400">{u}</span></p></div>
            ))}
            <div><p className="label">Last sample</p><p className="font-mono text-xl font-semibold">{f.lastUpdate ? fmtTime(f.lastUpdate) : '—'}</p></div>
          </div>
          <div className="space-y-4">
            <VoltageChart range={range} thresholds={thresholds} height={280} />
            <CurrentChart range={range} thresholds={thresholds} height={280} />
            <PowerChart range={range} height={280} />
          </div>
        </>
      )}
    </>
  );
}
