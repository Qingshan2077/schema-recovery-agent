import type { ConfidenceLevel } from "../../types/api";
import { confidenceLabel, confidenceLevel } from "../../utils/confidenceColor";

interface ConfidenceBadgeProps {
  confidence: number;
  size?: "sm" | "md" | "lg";
}

export function ConfidenceBadge({ confidence, size = "md" }: ConfidenceBadgeProps) {
  const level = confidenceLevel(confidence);
  return (
    <span className={`confidence-badge confidence-badge-${level} confidence-badge-${size}`}>
      {confidenceLabel(confidence)} {(confidence * 100).toFixed(0)}%
    </span>
  );
}

export function ConfidenceDot({ level }: { level: ConfidenceLevel }) {
  return <span className={`confidence-dot confidence-dot-${level}`} />;
}
