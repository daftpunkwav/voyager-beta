/**
 * graph-viz — L0 与 L1 共享的 R3F 可视化根层
 *
 * 将 code-graph 目录下的 3D 场景组件、类型与辅助工具统一从此处导出，
 * 使 L0 GraphPage 与 L1 CodeGraphPage 共用同一视觉根，避免重复实现。
 */
export { GraphScene, computeCameraTarget } from '@/components/code-graph/GraphScene';
export type { CameraTarget } from '@/components/code-graph/GraphScene';
export { NodeCloud } from '@/components/code-graph/NodeCloud';
export { EdgeLines } from '@/components/code-graph/EdgeLines';
export { NodeLabels } from '@/components/code-graph/NodeLabels';
export { NodeTooltipContent, NodeTooltipTracker, NodeTooltip } from '@/components/code-graph/NodeTooltip';
export type {
  CodeGraphNode,
  CodeGraphEdge,
  CodeGraphData,
  GraphNode,
  GraphEdge,
  GraphData,
  GraphIndexStatus,
  NodeStatus,
} from '@/components/code-graph/types';
export { toRenderGraph } from '@/components/code-graph/renderGraph';
export {
  colorForLabel,
  colorForStatus,
  STATUS_LEGEND,
} from '@/components/code-graph/colors';
export { projectGraphToScene, projectIdFromSceneNode } from '@/components/graph/l0Layout3d';
export { UniverseGraphView } from '@/components/graph/UniverseGraphView';
