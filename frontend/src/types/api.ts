export type ConfidenceLevel = "all" | "high" | "medium" | "low";
export type RunStatus = "queued" | "running" | "waiting_approval" | "partial" | "degraded" | "blocked" | "failed" | "canceled" | "completed" | "expired";

export interface EvidenceChainItem {
  evidence_id?: string;
  run_id?: string;
  trace_id?: string;
  snapshot_id?: string;
  type: string;
  weight: number;
  detail: string;
  strength: number;
}

export interface RelationDetail {
  relation_id?: string;
  run_id?: string;
  trace_id?: string;
  database_fingerprint?: string;
  snapshot_id?: string;
  evidence_ids?: string[];
  source_table: string;
  target_table: string;
  fk_column: string;
  pk_column: string;
  relation_type: string;
  fused_confidence: number;
  base_confidence?: number;
  synergy_bonus?: number;
  conflict_penalty?: number;
  confidence_reason?: string;
  evidence_count: number;
  evidence_sources: string[];
  evidence_chain: EvidenceChainItem[];
}

export interface ToolCallSummary {
  tool_call_id?: string;
  tool: string;
  params?: Record<string, unknown>;
  result_summary?: string;
}

export interface ERRelation {
  type: "has" | "referenced_by";
  target: string;
  via: string;
  confidence: number;
}

export interface TableNodeData {
  relations: ERRelation[];
  relation_count: number;
}

export interface ERDiagram {
  table_count: number;
  tables: Record<string, TableNodeData>;
}

export interface SurveyOutput {
  summary?: {
    total_tables: number;
    total_views: number;
    total_procedures: number;
    total_triggers: number;
    total_orm_files: number;
  };
  server_info?: {
    version?: string;
    database?: string;
    database_fingerprint?: string;
    snapshot_id?: string;
    schema_hash?: string;
  };
}

export interface AnalysisStep {
  step: number;
  worker: string;
  status: string;
  duration_ms: number;
  tool_calls?: ToolCallSummary[];
  output?: unknown;
  error?: string;
}

export interface MergeSummary {
  total_relations: number;
  high_confidence: number;
  medium_confidence: number;
  low_confidence: number;
}

export interface MergeResult {
  artifact_id?: string;
  run_id?: string;
  trace_id?: string;
  database_fingerprint?: string;
  snapshot_id?: string;
  summary: MergeSummary;
  high_confidence_relations: RelationDetail[];
  medium_confidence_relations: RelationDetail[];
  low_confidence_relations: RelationDetail[];
  source_contributions: Record<string, { count: number; percentage: number }>;
}

export interface AnalysisResult {
  session_id: string;
  run_id: string;
  trace_id: string;
  thread_id?: string;
  parent_run_id?: string;
  attempt?: number;
  status: RunStatus;
  run_status: RunStatus;
  snapshot_id?: string;
  database_fingerprint?: string;
  total_steps: number;
  steps: AnalysisStep[];
  er_diagram?: ERDiagram;
  merge_result?: MergeResult;
  capability_gaps?: Array<{
    worker?: string;
    status?: string;
    error?: string;
  }>;
  next_actions?: string[];
  graph?: {
    engine: string;
    started_at?: string;
    completed_workers?: string[];
    skipped_workers?: string[];
    errors?: string[];
    fallback_reason?: string;
    reason?: string;
  };
  error?: string;
  error_detail?: {
    code: string;
    message: string;
    retryable: boolean;
    details?: Record<string, unknown>;
  };
}

export interface AnalysisProgress {
  sessionId?: string;
  runId?: string;
  traceId?: string;
  lastSequence?: number;
  totalSteps: number;
  completedSteps: number;
  currentNode?: string;
  startedNodes: string[];
  steps: AnalysisStep[];
}

export interface StreamProgressEvent {
  type: "started" | "node_started" | "node_complete" | "complete" | "error" | "heartbeat";
  event_type?: string;
  event_id?: string;
  sequence?: number;
  timestamp?: string;
  session_id?: string;
  thread_id?: string;
  run_id?: string;
  trace_id?: string;
  span_id?: string;
  parent_span_id?: string;
  status?: RunStatus;
  schema_version?: string;
  total_steps?: number;
  node?: string;
  step?: AnalysisStep;
  progress?: {
    completed: number;
    total: number;
  };
  data?: AnalysisResult;
  payload?: Record<string, unknown>;
  error?: string;
}

export interface MonitorStats {
  total_analyses: number;
  legacy_unverified_analyses?: number;
  message?: string;
  avg_duration_ms?: number;
  avg_tables_per_analysis?: number;
  worker_stats?: Array<{
    worker_id: string;
    runs: number;
    avg_duration_ms: number;
    success_rate: number;
  }>;
  recent_analyses?: Array<{
    session_id: string;
    run_id?: string;
    trace_id?: string;
    snapshot_id?: string;
    status: string;
    duration_ms: number;
    high_confidence: number;
    date: string;
  }>;
}

export interface MemoryQueryResult {
  relations: RelationDetail[];
  history: Array<{
    id: number;
    session_id: string;
    database: string;
    date: string;
    tables: number;
    relations: number;
    high_confidence: number;
    summary: string;
  }>;
}

export interface EvalReport {
  report_id?: string;
  report_title: string;
  report_date: string;
  quantitative?: {
    description: string;
    precision: number;
    recall: number;
    f1_score: number;
    high_confidence_precision?: number;
    partial_fk_recall?: number;
    details: Record<string, number>;
    test_info?: Record<string, number>;
    metadata?: Record<string, unknown>;
    observed?: Record<string, number>;
    targets?: Record<string, number>;
  };
  qualitative?: unknown;
  monitor?: MonitorStats;
}

export interface ChatMessage {
  messageId?: string;
  role: "user" | "assistant" | "system";
  content: string;
  type?: ChatResponse["type"];
  pending?: Record<string, unknown>;
  safetyLevel?: "confirm" | "dangerous" | "safe";
  ddlExecuted?: string;
  newAnalysis?: AnalysisResult;
  structured?: QAOutput | Record<string, unknown>;
  createdAt?: string;
}

export interface QACitation {
  citation_id: string;
  claim_id: string;
  fact_ids: string[];
  label: string;
  locator: Record<string, unknown>;
}

export interface QAArtifact {
  artifact_id: string;
  type: "column_table" | "relation_cards" | "evidence_cards" | "clarification_options" | "metadata_card" | "index_table" | "overview";
  title: string;
  data: Record<string, unknown>;
  fact_ids: string[];
}

export interface QAEntityRef {
  mention: string;
  status: "resolved" | "ambiguous" | "not_found";
  canonical_name?: string;
  resolution_method: string;
  candidates: Array<{ entity_id: string; name: string; schema_name: string }>;
}

export interface QAOutput {
  answer?: string;
  intent: string;
  clarification_question?: string;
  entities: QAEntityRef[];
  citations: QACitation[];
  artifacts: QAArtifact[];
  citation_coverage?: number;
  degraded_reasons?: string[];
}

export interface ChatThreadResponse {
  thread_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: Array<{
    message_id: string;
    role: "user" | "assistant" | "system";
    content: string;
    structured?: QAOutput | Record<string, unknown>;
    created_at: string;
  }>;
  last_sequence: number;
}

export interface StartedQARun {
  thread_id: string;
  message_id: string;
  run_id: string;
  trace_id: string;
  status: "running";
  reused: boolean;
  events_url: string;
}

export interface ChatEventPage {
  events: Array<{
    event_id: string;
    run_id: string;
    event_type: string;
    status: RunStatus;
    payload: Record<string, unknown>;
  }>;
  next_sequence: number;
}

interface ChatIdentityFields {
  session_id: string;
  thread_id?: string;
  run_id?: string;
  trace_id?: string;
}

export type ChatResponse =
  | (ChatIdentityFields & {
      type: "answer" | "clarification";
      content: string;
      intent?: string;
      data?: unknown;
      qa_run_id?: string;
      citations?: QACitation[];
      artifacts?: QAArtifact[];
    })
  | (ChatIdentityFields & {
      type: "confirmation";
      message: string;
      pending?: Record<string, unknown>;
      safety_level?: "confirm" | "dangerous" | "safe";
    })
  | (ChatIdentityFields & {
      type: "result" | "error";
      message: string;
      ddl_executed?: string;
      new_analysis?: AnalysisResult;
      data?: unknown;
    });
