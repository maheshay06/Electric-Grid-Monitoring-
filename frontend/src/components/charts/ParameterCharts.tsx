import type { RangeKey, Thresholds } from '../../types';
import { getSeries } from '../../api/store';
import ChartCard from '../common/ChartCard';
import LiveLineChart from './LiveLineChart';

interface Props {
  range: RangeKey;
  thresholds: Thresholds;
  height?: number;
}

// Colours chosen to stay distinguishable for colour-blind viewers (blue / orange / teal).
const C = { v: '#6366F1', i: '#EA580C', p: '#0F766E' };

export function VoltageChart({ range, thresholds, height }: Props) {
  return (
    <ChartCard title="Real-Time Voltage" subtitle={'Voltage sensor · dashed = UV/OV limits'}>
      <LiveLineChart
        data={getSeries(1, range)} range={range} unit="V" height={height}
        series={[{ key: 'voltage', label: 'Voltage (V)', color: C.v }]}
        domain={[3.5, 6.5]}
        limits={[
          { y: thresholds.overvoltage, label: 'OV', color: '#DC2626' },
          { y: thresholds.undervoltage, label: 'UV', color: '#DC2626' },
        ]}
      />
    </ChartCard>
  );
}

export function CurrentChart({ range, thresholds, height }: Props) {
  return (
    <ChartCard title="Real-Time Current" subtitle={'ACS712 current sensor · dashed = OC limit'}>
      <LiveLineChart
        data={getSeries(1, range)} range={range} unit="A" height={height} digits={2}
        series={[{ key: 'current', label: 'Current (A)', color: C.i }]}
        domain={[0, 2.5]}
        limits={[{ y: thresholds.overcurrent, label: 'OC', color: '#DC2626' }]}
      />
    </ChartCard>
  );
}

export function PowerChart({ range, height }: Omit<Props, 'thresholds'>) {
  return (
    <ChartCard title="Active Power" subtitle={'P = V × I'}>
      <LiveLineChart
        data={getSeries(1, range)} range={range} unit="W" height={height}
        series={[{ key: 'power', label: 'Power (W)', color: C.p }]}
        domain={[0, 'auto']}
      />
    </ChartCard>
  );
}
