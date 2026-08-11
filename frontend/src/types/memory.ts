export interface MemorySummary {
  memory_id: string;
  layer: "l2" | "l3";
  current_version: number;
  status: string;
  created_by_run_id?: string | null;
  created_at: string;
}

export interface MemoryListResponse {
  trace_id?: string | null;
  namespace: Record<string, unknown>;
  items: MemorySummary[];
}

export interface MemoryDetail {
  memory_id: string;
  version: number;
  status?: string;
  lifecycle?: string;
  summary?: string;
  rule_summary?: string;
  evidence_ids?: string[];
  root_fact_ids?: string[];
  calibrated_probability?: number;
  calibration_version?: string;
  [key: string]: unknown;
}
