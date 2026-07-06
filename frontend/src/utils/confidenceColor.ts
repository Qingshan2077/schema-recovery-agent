import type { ConfidenceLevel } from "../types/api";

export function confidenceLevel(confidence: number): Exclude<ConfidenceLevel, "all"> {
  if (confidence >= 0.7) return "high";
  if (confidence >= 0.4) return "medium";
  return "low";
}

export function confidenceLabel(confidence: number): string {
  const level = confidenceLevel(confidence);
  if (level === "high") return "高置信度";
  if (level === "medium") return "中置信度";
  return "低置信度";
}

export function confidenceColor(confidence: number): string {
  const level = confidenceLevel(confidence);
  if (level === "high") return "#22c55e";
  if (level === "medium") return "#eab308";
  return "#ef4444";
}

export function confidenceClass(confidence: number): string {
  return `confidence-${confidenceLevel(confidence)}`;
}

export function relationPassesFilter(confidence: number, filter: ConfidenceLevel): boolean {
  return filter === "all" || confidenceLevel(confidence) === filter;
}
