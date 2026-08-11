export interface DomainEvent { sequence: number; type: string; timestamp?: string; trace_id?: string; span_id?: string; status?: string; [key: string]: unknown; }
export interface EventState { cursor: number; gap: { expected: number; received: number } | null; events: DomainEvent[]; }
