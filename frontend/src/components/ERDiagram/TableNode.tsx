import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Table2 } from "lucide-react";
import type { TableNodePayload } from "../../utils/graphLayout";

export function TableNode({ data }: NodeProps) {
  const nodeData = data as TableNodePayload;
  return (
    <div className="table-node">
      <Handle type="target" position={Position.Left} />
      <div className="table-node-title">
        <Table2 size={16} />
        <span>{nodeData.label}</span>
      </div>
      <small>{nodeData.relationCount} relations</small>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
