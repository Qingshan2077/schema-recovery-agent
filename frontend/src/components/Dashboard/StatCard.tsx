import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  color?: "green" | "yellow" | "red" | "blue" | "slate";
  icon?: LucideIcon;
}

export function StatCard({ title, value, subtitle, color = "slate", icon: Icon }: StatCardProps) {
  return (
    <div className={`stat-card stat-card-${color}`}>
      <div className="stat-card-header">
        <span>{title}</span>
        {Icon ? <Icon size={18} /> : null}
      </div>
      <strong>{value}</strong>
      {subtitle ? <small>{subtitle}</small> : null}
    </div>
  );
}
