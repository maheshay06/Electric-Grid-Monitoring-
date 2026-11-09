export type FeederState = 'NORMAL' | 'TRIPPED' | 'OFFLINE' | 'NOT_INSTALLED';
export type RelayState = 'ENERGISED' | 'RELEASED' | 'UNKNOWN';
export type LoadState = 'CONNECTED' | 'DISCONNECTED' | 'UNKNOWN';
export type Health = 'OK' | 'WARNING' | 'FAULT' | 'OFFLINE' | 'N/A';
export type Severity = 'None' | 'Low' | 'Medium' | 'High' | 'Critical';
export type RangeKey = '1m' | '5m' | '15m' | '1h' | '24h';

export type FaultClass = 'NORMAL' | 'UNDERVOLTAGE' | 'OVERVOLTAGE' | 'OVERCURRENT' | 'ABNORMAL CONDITION';
export type EventType = 'UNDERVOLTAGE' | 'OVERVOLTAGE' | 'OVERCURRENT' | 'TRIPPED' | 'RESTORED' | 'DEVICE_OFFLINE';
export type EventSource = 'RULE' | 'OPERATOR' | 'PUSHBUTTON' | 'SYSTEM';
export type EventStatus = 'ACTIVE' | 'CLEARED' | 'ACKNOWLEDGED';

export interface Reading {
  ts: number; // epoch ms
  voltage: number;
  current: number;
  power: number;
}

export interface Feeder {
  id: number;
  name: string;
  primary: boolean;
  installed: boolean;
  state: FeederState;
  relay: RelayState; // as REPORTED by the device, never inferred from a command
  load: LoadState;
  voltage: number;
  current: number;
  power: number;
  health: Health;
  simulated: boolean;
  lastUpdate: number | null;
}

export interface FaultEvent {
  id: string;
  feederId: number;
  ts: number;
  type: EventType;
  severity: Severity;
  voltage: number;
  current: number;
  source: EventSource;
  status: EventStatus;
  clearedAt?: number;
  simulated: boolean;
}

export type CommandAction = 'TRIP' | 'RESTORE';
export type CommandStatus = 'PENDING' | 'SENT' | 'ACKED' | 'FAILED' | 'TIMEOUT' | 'REJECTED';

export interface Command {
  id: string;
  feederId: number;
  action: CommandAction;
  source: 'OPERATOR';
  requestedBy: string;
  status: CommandStatus;
  createdAt: number;
  sentAt?: number;
  ackedAt?: number;
  reason?: string;
  simulatedAck: boolean;
}

export interface Prediction {
  ts: number;
  feederId: number;
  cls: FaultClass;
  confidence: number; // 0..1
  severity: Severity;
  voltage: number;
  current: number;
  power: number;
}

export interface AppNotification {
  id: string;
  ts: number;
  kind: 'FAULT' | 'TRIP' | 'RESTORE' | 'DEVICE' | 'AI_ADVISORY' | 'SYSTEM';
  severity: Severity;
  title: string;
  message: string;
  feederId?: number;
  read: boolean;
}

export interface Thresholds {
  nominal: number;
  undervoltage: number;
  overvoltage: number;
  overcurrent: number;
}

export interface User {
  operatorId: string;
  name: string;
  role: 'admin' | 'operator' | 'viewer';
  locationId: string;
}
