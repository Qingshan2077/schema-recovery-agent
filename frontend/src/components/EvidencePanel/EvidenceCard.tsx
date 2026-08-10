import { Code2, Database, FileCode2, Fingerprint, Network } from "lucide-react";
import { useI18n } from "../../i18n/LanguageContext";
import type { EvidenceChainItem } from "../../types/api";

interface EvidenceCardProps {
  item: EvidenceChainItem;
  index: number;
}

const iconMap = {
  sql_join: Code2,
  orm_association: FileCode2,
  orm_collection: FileCode2,
  column_name_suffix: Database,
  primary_key_name_match: Database,
  naming_convention_match: Fingerprint,
  naming_cross_table: Fingerprint,
  index_exists: Network
};

export function EvidenceCard({ item, index }: EvidenceCardProps) {
  const { t } = useI18n();
  const Icon = iconMap[item.type as keyof typeof iconMap] ?? Database;
  return (
    <article className={`evidence-card evidence-${item.type}`}>
      <header>
        <div>
          <Icon size={16} />
          <strong>{index + 1}. {formatEvidenceType(item.type)}</strong>
        </div>
        <span>{t("weight")} {item.weight.toFixed(2)}</span>
      </header>
      <p>{item.detail || t("noEvidenceDetail")}</p>
      <footer>{t("evidenceStrength")} {(item.strength * 100).toFixed(0)}%</footer>
    </article>
  );
}

function formatEvidenceType(type: string): string {
  return type.replaceAll("_", " ").replace(/\b\w/g, (value) => value.toUpperCase());
}
