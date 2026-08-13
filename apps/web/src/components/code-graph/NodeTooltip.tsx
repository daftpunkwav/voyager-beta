import type { RefObject } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import type { GraphNode } from './types';
import { colorForLabel, colorForStatus } from './colors';
import {
  computeTooltipScreenScale,
  layoutTooltipInViewport,
  measureGraphOverlayInsets,
  tooltipAnchorY,
} from './graphTooltipScale';

const _projected = new THREE.Vector3();
const _world = new THREE.Vector3();

interface NodeTooltipContentProps {
  node: GraphNode;
}

function lineRange(node: GraphNode): string | null {
  if (!node.start_line) return null;
  if (node.end_line && node.end_line !== node.start_line) {
    return `L${node.start_line}–${node.end_line}`;
  }
  return `L${node.start_line}`;
}

/** 悬停卡片 DOM（须在 Canvas 外渲染） */
export function NodeTooltipContent({ node }: NodeTooltipContentProps) {
  const isProject = node.kind === 'Project' || node.label === 'Project';
  const lines = lineRange(node);

  return (
    <>
      <div className="code-graph-tooltip__row">
        <span
          className="code-graph-tooltip__dot"
          style={{ backgroundColor: node.color || colorForLabel(node.label) }}
        />
        <span className="code-graph-tooltip__name">{node.name}</span>
        <span className="code-graph-tooltip__kind">
          {isProject ? 'Project' : node.kind || node.label}
        </span>
      </div>
      {isProject && node.file_path && (
        <p className="code-graph-tooltip__path">{node.file_path}</p>
      )}
      {!isProject && node.file_path && (
        <p className="code-graph-tooltip__path">
          {node.file_path}
          {lines ? ` · ${lines}` : ''}
        </p>
      )}
      {node.status && node.status !== 'structural' && node.status !== 'normal' && (
        <div className="code-graph-tooltip__row">
          <span
            className="code-graph-tooltip__dot"
            style={{ backgroundColor: colorForStatus(node.status) }}
          />
          <span>{node.status}</span>
        </div>
      )}
      {typeof node.relatedness === 'number' && (
        <p className="code-graph-tooltip__meta">
          关联度 {node.relatedness.toFixed(2)}
        </p>
      )}
      {typeof node.relatedness !== 'number' &&
        !isProject &&
        typeof node.in_calls === 'number' &&
        node.in_calls > 0 && (
          <p className="code-graph-tooltip__meta">入度 {node.in_calls}</p>
        )}
      <p className="code-graph-tooltip__hint">
        {isProject ? '单击选中 · 双击进入代码图谱' : '单击查看详情'}
      </p>
    </>
  );
}

interface NodeTooltipTrackerProps {
  node: GraphNode;
  tooltipRef: RefObject<HTMLDivElement | null>;
}

/** Canvas 内仅跟踪相机并更新外部 DOM 位置，不渲染 HTML */
export function NodeTooltipTracker({ node, tooltipRef }: NodeTooltipTrackerProps) {
  const { camera, size, gl } = useThree();

  useFrame(() => {
    const el = tooltipRef.current;
    if (!el) return;

    _world.set(node.x, tooltipAnchorY(node), node.z);
    const dist = camera.position.distanceTo(_world);
    _projected.copy(_world).project(camera);

    if (_projected.z > 1) {
      el.style.visibility = 'hidden';
      return;
    }

    const canvasEl = gl.domElement.parentElement;
    const insets = canvasEl
      ? measureGraphOverlayInsets(canvasEl)
      : undefined;

    const anchorX = (_projected.x * 0.5 + 0.5) * size.width;
    const anchorY = (-_projected.y * 0.5 + 0.5) * size.height;
    const scale = computeTooltipScreenScale(dist);
    const layout = layoutTooltipInViewport({
      anchorX,
      anchorY,
      boxW: el.offsetWidth || 160,
      boxH: el.offsetHeight || 72,
      viewW: size.width,
      viewH: size.height,
      scale,
      insets,
    });

    el.style.visibility = 'visible';
    el.style.left = `${layout.left}px`;
    el.style.top = `${layout.top}px`;
    el.style.transform = layout.transform;
  });

  return null;
}

/** @deprecated 请使用 NodeTooltipContent + NodeTooltipTracker */
export function NodeTooltip({ node }: NodeTooltipContentProps) {
  return <NodeTooltipContent node={node} />;
}
