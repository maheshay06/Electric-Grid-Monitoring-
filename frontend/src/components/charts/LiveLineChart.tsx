import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { RangeKey, Reading } from '../../types';
import { fmtTime } from '../../utils/format';

export interface SeriesDef {
  key: 'voltage' | 'current' | 'power';
  label: string;
  color: string;
}

interface Props {
  data: Reading[];
  series: SeriesDef[];
  unit: string;
  range: RangeKey;
  height?: number;
  domain?: [number | 'auto', number | 'auto'];
  limits?: { y: number; label: string; color: string }[];
  digits?: number;
}

export default function LiveLineChart({ data, series, unit, range, height = 240, domain, limits = [], digits = 2 }: Props) {
  if (data.length === 0) {
    return <div className="flex items-center justify-center rounded-lg bg-slate-50 text-sm text-slate-500" style={{ height }}>No data for this range</div>;
  }
  return (
    <div style={{ height }} role="img" aria-label={`${series.map((s) => s.label).join(', ')} over the last ${range}`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 6, right: 12, bottom: 0, left: -8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
          <XAxis dataKey="ts" type="number" scale="time" domain={['dataMin', 'dataMax']} tickFormatter={(t) => fmtTime(t as number, range === '1m' || range === '5m')} tick={{ fontSize: 11, fill: '#64748B' }} minTickGap={40} />
          <YAxis domain={domain ?? ['auto', 'auto']} tick={{ fontSize: 11, fill: '#64748B' }} width={46} tickFormatter={(v) => Number(v).toFixed(digits === 0 ? 0 : 1)} />
          <Tooltip
            labelFormatter={(t) => fmtTime(t as number)}
            formatter={(v: number, n: string) => [`${v.toFixed(digits + 1)} ${unit}`, n]}
            contentStyle={{ borderRadius: 10, border: '1px solid #E2E8F0', fontSize: 12 }}
          />
          {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
          {limits.map((l) => (
            <ReferenceLine key={l.label} y={l.y} stroke={l.color} strokeDasharray="5 4" label={{ value: l.label, position: 'insideTopRight', fontSize: 10, fill: l.color }} />
          ))}
          {series.map((s) => (
            <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={s.color} strokeWidth={2} dot={false} isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
