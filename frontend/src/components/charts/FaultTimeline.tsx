import { useMemo } from 'react';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { FaultEvent, RangeKey } from '../../types';
import { RANGE_SECONDS, fmtTime } from '../../utils/format';
import ChartCard from '../common/ChartCard';

const BUCKETS = 12;

export default function FaultTimeline({ events, range }: { events: FaultEvent[]; range: RangeKey }) {
  const data = useMemo(() => {
    const span = RANGE_SECONDS[range] * 1000;
    const end = Date.now();
    const start = end - span;
    const size = span / BUCKETS;
    const rows = Array.from({ length: BUCKETS }, (_, i) => ({ ts: start + i * size, Faults: 0, Trips: 0 }));
    events.forEach((e) => {
      if (e.ts < start) return;
      const idx = Math.min(BUCKETS - 1, Math.floor((e.ts - start) / size));
      if (e.type === 'TRIPPED') rows[idx].Trips++;
      else if (e.type !== 'RESTORED') rows[idx].Faults++;
    });
    return rows;
  }, [events, range]);

  return (
    <ChartCard title="Fault Occurrence Timeline" subtitle="Events per time bucket (selected range)">
      <div style={{ height: 200 }} role="img" aria-label="Fault and trip counts over time">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 6, right: 12, bottom: 0, left: -20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
            <XAxis dataKey="ts" tickFormatter={(t) => fmtTime(t as number, false)} tick={{ fontSize: 11, fill: '#64748B' }} />
            <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#64748B' }} />
            <Tooltip labelFormatter={(t) => fmtTime(t as number)} contentStyle={{ borderRadius: 10, fontSize: 12 }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="Faults" stackId="a" fill="#EA580C" radius={[0, 0, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="Trips" stackId="a" fill="#DC2626" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
