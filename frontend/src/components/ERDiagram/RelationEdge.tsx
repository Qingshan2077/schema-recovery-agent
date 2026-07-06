import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps
} from "@xyflow/react";
import type { RelationEdgePayload } from "../../utils/graphLayout";
import { confidenceColor } from "../../utils/confidenceColor";

export function RelationEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data
}: EdgeProps) {
  const edgeData = data as RelationEdgePayload | undefined;
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition
  });
  const confidence = edgeData?.confidence ?? 0;

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{ stroke: confidenceColor(confidence), strokeWidth: confidence >= 0.7 ? 2.5 : 1.8 }}
      />
      <EdgeLabelRenderer>
        <div
          className="edge-label"
          style={{
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            borderColor: confidenceColor(confidence)
          }}
        >
          {edgeData?.label}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}
