import { X } from "lucide-react";
import type { RelationDetail } from "../../types/api";
import { ConfidenceBadge } from "../common/ConfidenceBadge";
import { EvidenceCard } from "./EvidenceCard";

interface EvidenceSidebarProps {
  relation?: RelationDetail;
  onClose: () => void;
}

export function EvidenceSidebar({ relation, onClose }: EvidenceSidebarProps) {
  return (
    <aside className={`evidence-sidebar ${relation ? "open" : ""}`} aria-hidden={!relation}>
      {relation ? (
        <>
          <header className="evidence-sidebar-header">
            <button className="icon-button" type="button" onClick={onClose} aria-label="关闭证据侧栏">
              <X size={18} />
            </button>
            <span>关系详情</span>
          </header>
          <div className="relation-summary">
            <h2>{relation.source_table}.{relation.fk_column}</h2>
            <div className="relation-arrow">-&gt;</div>
            <h2>{relation.target_table}.{relation.pk_column}</h2>
            <div className="relation-meta">
              <ConfidenceBadge confidence={relation.fused_confidence} />
              <span>{relation.relation_type}</span>
              <span>{relation.evidence_count} 条证据</span>
            </div>
            {relation.confidence_reason ? (
              <div className="confidence-reason">
                <strong>置信度解释</strong>
                <p>{relation.confidence_reason}</p>
                <div className="confidence-breakdown">
                  <span>base {formatNumber(relation.base_confidence)}</span>
                  <span>bonus {formatNumber(relation.synergy_bonus)}</span>
                  <span>penalty {formatNumber(relation.conflict_penalty)}</span>
                </div>
              </div>
            ) : null}
          </div>
          <section className="evidence-list">
            <h3>证据链</h3>
            {relation.evidence_chain.length ? (
              relation.evidence_chain.map((item, index) => (
                <EvidenceCard item={item} index={index} key={`${item.type}-${index}`} />
              ))
            ) : (
              <div className="table-empty">没有可展示的证据链</div>
            )}
          </section>
        </>
      ) : null}
    </aside>
  );
}

function formatNumber(value?: number): string {
  return typeof value === "number" ? value.toFixed(2) : "-";
}
