import { useI18n, type TranslationKey } from "../../i18n/LanguageContext";
import type { ConfidenceLevel } from "../../types/api";
import { confidenceLevel } from "../../utils/confidenceColor";

interface ConfidenceBadgeProps {
  confidence: number;
  size?: "sm" | "md" | "lg";
}

const confidenceLabelKeys: Record<Exclude<ConfidenceLevel, "all">, TranslationKey> = {
  high: "highConfidence",
  medium: "mediumConfidence",
  low: "lowConfidence"
};

export function ConfidenceBadge({ confidence, size = "md" }: ConfidenceBadgeProps) {
  const { t } = useI18n();
  const level = confidenceLevel(confidence);
  return (
    <span className={`confidence-badge confidence-badge-${level} confidence-badge-${size}`}>
      {t(confidenceLabelKeys[level])} {(confidence * 100).toFixed(0)}%
    </span>
  );
}

export function ConfidenceDot({ level }: { level: ConfidenceLevel }) {
  return <span className={`confidence-dot confidence-dot-${level}`} />;
}
