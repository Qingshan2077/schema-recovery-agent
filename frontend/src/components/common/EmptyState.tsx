import { Database, Play } from "lucide-react";

interface EmptyStateProps {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function EmptyState({ title, description, actionLabel, onAction }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <Database size={34} />
      <div>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      {actionLabel && onAction ? (
        <button className="primary-button" type="button" onClick={onAction}>
          <Play size={16} />
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}
