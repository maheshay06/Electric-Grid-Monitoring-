import { useMemo, useState } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { getSeries, useEngine } from '../api/store';
import type { RangeKey } from '../types';
import PageHeader from '../components/common/PageHeader';
import RangeSelector from '../components/common/RangeSelector';
import ChartCard from '../components/common/ChartCard';
import EmptyState from '../components/common/EmptyState';
import { CurrentChart, PowerChart, VoltageChart } from '../components/charts/ParameterCharts';
import { fmt, RANGE_SECONDS } from '../utils/format';

export default function AnalyticsPage() {
  const { faults, thresholds } = useEngine();
  const [range, setRange] = useState<RangeKey>('24h');

  const series = getSeries(1, range);
  const stats = (k: 'voltage' | 'current' | 'power') => {
    if (!series.length) return { min: NaN, max: NaN, avg: NaN };
    const v = series.map((r) => r[k]);
    return { min: Math.min(...v), max: Math.max(...v), avg: v.reduce((a, b) => a + b, 0) / v.length };
  };

  const counts = useMemo(() => {
    const cutoff = Date.now() - RANGE_SECONDS[range] * 1000;
    const m: Record<string, number> = {};
    faults.filter((e) => e.ts >= cutoff).forEach((e) => { m[e.type] = (m[e.type] ?? 0) + 1; });
    return Object.entries(m).map(([type, count]) => ({ type, count }));
  }, [faults, range]);

  return (
    <>
      <PageHeader title="Analytics" subtitle="Trends and summary statistics">
        <RangeSelector value={range} onChange={setRange} />
      </PageHeader>

      {series.length === 0 ? (
        <EmptyState title="No data to analyse">Analytics need stored readings. Enable Demo Mode or connect the ESP32.</EmptyState>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            {([['Voltage', 'voltage', 'V', 3], ['Current', 'current', 'A', 3], ['Power', 'power', 'W', 3]] as const).map(([label, k, u, d]) => {
              const s = stats(k);
              return (
                <div key={k} className="card p-4">
                  <p className="text-sm font-semibold text-navy-900">{label} ({u})</p>
                  <dl className="mt-2 grid grid-cols-3 text-center font-mono text-sm">
                    {[['Min', s.min], ['Avg', s.avg], ['Max', s.max]].map(([n, val]) => (
                      <div key={n as string}><dt className="font-sans text-[11px] text-slate-500">{n}</dt><dd className="font-semibold">{fmt(val as number, d)}</dd></div>
                    ))}
                  </dl>
                </div>
              );
            })}
          </div>
          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <VoltageChart range={range} thresholds={thresholds} />
            <CurrentChart range={range} thresholds={thresholds} />
            <PowerChart range={range} />
            <ChartCard title="Events by Type" subtitle="Selected range">
              {counts.length === 0 ? <p className="py-16 text-center text-sm text-slate-500">No events in this range.</p> : (
                <div style={{ height: 240 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={counts} margin={{ top: 6, right: 12, bottom: 0, left: -20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                      <XAxis dataKey="type" tick={{ fontSize: 10, fill: '#64748B' }} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#64748B' }} />
                      <Tooltip contentStyle={{ borderRadius: 10, fontSize: 12 }} />
                      <Bar dataKey="count" fill="#1D4ED8" radius={[4, 4, 0, 0]} isAnimationActive={false} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </ChartCard>
          </div>
        </>
      )}
    </>
  );
}
