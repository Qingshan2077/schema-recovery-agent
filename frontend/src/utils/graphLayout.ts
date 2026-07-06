import type { Edge, Node } from "@xyflow/react";
import type { ConfidenceLevel, ERDiagram, RelationDetail } from "../types/api";
import { confidenceColor, relationPassesFilter } from "./confidenceColor";

export interface TableNodePayload {
  label: string;
  relationCount: number;
}

export interface RelationEdgePayload {
  label: string;
  confidence: number;
  relation?: RelationDetail;
}

export function buildRelationIndex(relations: RelationDetail[]): Map<string, RelationDetail> {
  const index = new Map<string, RelationDetail>();
  for (const relation of relations) {
    index.set(relationKey(relation.source_table, relation.target_table, relation.fk_column), relation);
  }
  return index;
}

export function relationKey(source: string, target: string, fkColumn: string): string {
  return `${source.toLowerCase()}::${target.toLowerCase()}::${fkColumn.toLowerCase()}`;
}

export function buildGraph(
  diagram: ERDiagram | undefined,
  relations: RelationDetail[],
  filter: ConfidenceLevel
): { nodes: Node<TableNodePayload>[]; edges: Edge<RelationEdgePayload>[] } {
  if (!diagram) return { nodes: [], edges: [] };

  const relationIndex = buildRelationIndex(relations);
  const tableNames = Object.keys(diagram.tables);
  const nodes = tableNames.map((tableName, index) => {
    const position = tablePosition(tableName, index, tableNames.length);
    return {
      id: tableName,
      type: "tableNode",
      position,
      data: {
        label: tableName,
        relationCount: diagram.tables[tableName].relation_count
      }
    };
  });

  const edges: Edge<RelationEdgePayload>[] = [];
  for (const [source, nodeData] of Object.entries(diagram.tables)) {
    for (const relation of nodeData.relations) {
      if (!relationPassesFilter(relation.confidence, filter)) continue;
      const fullRelation = relationIndex.get(relationKey(source, relation.target, relation.via));
      edges.push({
        id: relationKey(source, relation.target, relation.via),
        source,
        target: relation.target,
        type: "relationEdge",
        animated: relation.confidence >= 0.7,
        data: {
          label: relation.via,
          confidence: relation.confidence,
          relation: fullRelation
        },
        style: {
          stroke: confidenceColor(relation.confidence),
          strokeWidth: relation.confidence >= 0.7 ? 2.5 : 1.8
        }
      });
    }
  }

  return { nodes, edges };
}

function tablePosition(tableName: string, index: number, total: number): { x: number; y: number } {
  const anchors: Record<string, { x: number; y: number }> = {
    users: { x: 80, y: 180 },
    orders: { x: 430, y: 190 },
    order_items: { x: 770, y: 210 },
    products: { x: 760, y: 420 },
    categories: { x: 1090, y: 420 },
    coupons: { x: 430, y: 20 },
    warehouses: { x: 1090, y: 650 },
    suppliers: { x: 1090, y: 230 }
  };
  if (anchors[tableName]) return anchors[tableName];

  const column = index % 5;
  const row = Math.floor(index / 5);
  const stagger = row % 2 ? 70 : 0;
  const width = Math.max(5, Math.ceil(Math.sqrt(total)));
  return {
    x: 90 + ((column + row) % width) * 245 + stagger,
    y: 80 + row * 145
  };
}
