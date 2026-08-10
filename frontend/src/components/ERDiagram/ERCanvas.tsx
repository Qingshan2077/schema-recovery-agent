import { useEffect } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  useEdgesState,
  useNodesState
} from "@xyflow/react";
import { useI18n } from "../../i18n/LanguageContext";
import type { ConfidenceLevel, ERDiagram, RelationDetail } from "../../types/api";
import { buildGraph, relationKey, type RelationEdgePayload, type TableNodePayload } from "../../utils/graphLayout";
import { ConfidenceDot } from "../common/ConfidenceBadge";
import { RelationEdge } from "./RelationEdge";
import { TableNode } from "./TableNode";

interface ERCanvasProps {
  diagram?: ERDiagram;
  relations: RelationDetail[];
  filter: ConfidenceLevel;
  selectedRelation?: RelationDetail;
  onFilterChange: (filter: ConfidenceLevel) => void;
  onRelationSelect: (relation?: RelationDetail) => void;
}

const nodeTypes = { tableNode: TableNode };
const edgeTypes = { relationEdge: RelationEdge };

const filterLabels: Record<ConfidenceLevel, "all" | "high" | "medium" | "low"> = {
  all: "all",
  high: "high",
  medium: "medium",
  low: "low"
};

export function ERCanvas({ diagram, relations, filter, selectedRelation, onFilterChange, onRelationSelect }: ERCanvasProps) {
  const { t } = useI18n();
  const [nodes, setNodes, onNodesChange] = useNodesState<TableNodePayload>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<RelationEdgePayload>([]);
  const selectedEdgeId = selectedRelation ? relationKey(selectedRelation.source_table, selectedRelation.target_table, selectedRelation.fk_column) : undefined;

  useEffect(() => {
    const nextGraph = buildGraph(diagram, relations, filter);
    setNodes((currentNodes) => {
      const currentPositions = new Map(currentNodes.map((node) => [node.id, node.position]));
      return nextGraph.nodes.map((node) => ({
        ...node,
        position: currentPositions.get(node.id) ?? node.position,
        draggable: true
      }));
    });
    setEdges(nextGraph.edges.map((edge) => ({ ...edge, selected: edge.id === selectedEdgeId })));
  }, [diagram, filter, relations, selectedEdgeId, setEdges, setNodes]);

  useEffect(() => {
    setEdges((currentEdges) => currentEdges.map((edge) => ({ ...edge, selected: edge.id === selectedEdgeId })));
  }, [selectedEdgeId, setEdges]);

  return (
    <section className="er-section">
      <div className="section-toolbar">
        <div>
          <h2>{t("erDiagram")}</h2>
          <p>{t("visibleRelations", { tables: nodes.length, relations: edges.length })}</p>
        </div>
        <div className="segmented-control" role="group" aria-label={t("confidenceFilter")}>
          {(["all", "high", "medium", "low"] as ConfidenceLevel[]).map((item) => (
            <button className={filter === item ? "active" : ""} type="button" key={item} onClick={() => onFilterChange(item)}>
              <ConfidenceDot level={item} />
              {t(filterLabels[item])}
            </button>
          ))}
        </div>
      </div>
      <div className="er-canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          minZoom={0.25}
          maxZoom={1.6}
          nodesDraggable
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onEdgeClick={(_, edge) => onRelationSelect((edge as Edge<RelationEdgePayload>).data?.relation)}
          onPaneClick={() => onRelationSelect(undefined)}
        >
          <Background gap={18} />
          <MiniMap pannable zoomable />
          <Controls />
        </ReactFlow>
      </div>
    </section>
  );
}
