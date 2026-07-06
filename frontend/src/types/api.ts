export type ConfidenceLevel = "all" | "high" | "medium" | "low";

export interface EvidenceChainItem {
  type: string;
  weight: number;
  detail: string;
  strength: number;
}

export interface RelationDetail {
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
  summary: MergeSummary;
  high_confidence_relations: RelationDetail[];
  medium_confidence_relations: RelationDetail[];
  low_confidence_relations: RelationDetail[];
  source_contributions: Record<string, { count: number; percentage: number }>;
}

export interface AnalysisResult {
  session_id: string;
  status: string;
  total_steps: number;
  steps: AnalysisStep[];
  er_diagram?: ERDiagram;
  merge_result?: MergeResult;
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
}

export interface AnalysisProgress {
  sessionId?: string;
  totalSteps: number;
  completedSteps: number;
  currentNode?: string;
  startedNodes: string[];
  steps: AnalysisStep[];
}

export interface StreamProgressEvent {
  type: "started" | "node_started" | "node_complete" | "complete" | "error";
  session_id?: string;
  total_steps?: number;
  node?: string;
  step?: AnalysisStep;
  progress?: {
    completed: number;
    total: number;
  };
  data?: AnalysisResult;
  error?: string;
}

export interface MonitorStats {
  total_analyses: number;
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
    metadata?: Record<string, string>;
  };
  qualitative?: unknown;
  monitor?: MonitorStats;
}
