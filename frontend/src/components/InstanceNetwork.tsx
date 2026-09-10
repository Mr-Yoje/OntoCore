import { TypeNetwork, type NetworkEdge, type NetworkNode, type NetworkSelect } from "./TypeNetwork";

export function InstanceNetwork({
  nodes,
  edges,
  onSelect,
}: {
  nodes: NetworkNode[];
  edges: NetworkEdge[];
  onSelect: NetworkSelect;
}) {
  return (
    <TypeNetwork nodes={nodes} edges={edges} onSelect={onSelect} emptyText="还没有实例" />
  );
}
