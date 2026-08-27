/** 图谱画布:d3 force 渲染;单击节点 -> 详情;双击 -> 邻居展开(L1)。
 *
 * 节点按 label 着色,选中/搜索高亮;超过阈值显示大图告警条(坑 3)。
 * d3 操作 DOM,React 只负责容器与告警;simulation 生命周期跟随挂载。
 */

import { useEffect, useMemo, useRef } from 'react';
import * as d3 from 'd3';
import { deriveGraph, LARGE_GRAPH_WARN, useGraphStore } from './graphStore';
import type { GraphEdge, GraphNode } from './graphStore';

const LABEL_COLORS: Record<string, string> = {
  Project: '#0064d6',
  Module: '#5e5ce6',
  File: '#8e8e93',
  Folder: '#aeaeb2',
  Class: '#bf5af2',
  Function: '#30d158',
  Method: '#2e8dff',
  Concept: '#ff9f0a',
  Term: '#64d2ff',
  Section: '#ffd60a',
};
const FALLBACK_COLOR = '#aeaeb2';

export function labelColor(label: string): string {
  return LABEL_COLORS[label] ?? FALLBACK_COLOR;
}

/** d3 模拟节点:GraphNode + 布局坐标(force 会挂 x/y/vx/vy)。 */
type SimNode = GraphNode & d3.SimulationNodeDatum;
/** d3 链接:d3 收敛后 source/target 会被替换为节点对象。 */
type SimLink = { edge: GraphEdge; source: string | SimNode; target: string | SimNode };

export function GraphCanvas() {
  const nodesMap = useGraphStore((s) => s.nodes);
  const edgesMap = useGraphStore((s) => s.edges);
  const highlight = useGraphStore((s) => s.highlight);
  const select = useGraphStore((s) => s.select);
  const expand = useGraphStore((s) => s.expand);
  const svgRef = useRef<SVGSVGElement>(null);

  const { nodes, links } = useMemo(
    () => deriveGraph({ nodes: nodesMap, edges: edgesMap }),
    [nodesMap, edgesMap],
  );
  const tooLarge = nodes.length > LARGE_GRAPH_WARN;

  useEffect(() => {
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();
    if (nodes.length === 0) return;

    const width = svgRef.current?.clientWidth || 800;
    const height = svgRef.current?.clientHeight || 520;

    const simNodes = nodes.map((n) => ({ ...n })) as SimNode[];
    const simLinks = links.map((l) => ({ ...l })) as SimLink[];

    const sim = d3
      .forceSimulation(simNodes)
      .force('link', d3
        .forceLink<SimNode, SimLink>(simLinks)
        .id((d) => d.id)
        .distance(70)
        .strength(0.15))
      .force('charge', d3.forceManyBody().strength(-160))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collide', d3.forceCollide(16))
      .alphaDecay(0.03);

    const link = svg
      .append('g')
      .selectAll('line')
      .data(simLinks)
      .join('line')
      .attr('stroke', 'var(--bg-300)')
      .attr('stroke-width', 1);

    const node = svg
      .append('g')
      .selectAll<SVGCircleElement, SimNode>('circle')
      .data(simNodes)
      .join('circle')
      .attr('r', (d) => (d.label === 'Project' ? 12 : 7))
      .attr('fill', (d) => labelColor(d.label))
      .attr('stroke', (d) => (highlight.has(d.id) ? 'var(--warning)' : 'var(--bg-50)'))
      .attr('stroke-width', (d) => (highlight.has(d.id) ? 3 : 1.5))
      .style('cursor', 'pointer')
      .call(
        d3
          .drag<SVGCircleElement, SimNode>()
          .on('start', (event, d) => {
            if (!event.active) sim.alphaTarget(0.25).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on('drag', (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on('end', (event, d) => {
            if (!event.active) sim.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          }),
      );

    const label = svg
      .append('g')
      .selectAll('text')
      .data(simNodes)
      .join('text')
      .text((d) => d.name)
      .attr('font-size', 10)
      .attr('fill', 'var(--text-600)')
      .attr('text-anchor', 'middle')
      .attr('pointer-events', 'none')
      .attr('dy', (d) => (d.label === 'Project' ? 24 : 18));

    node
      .on('click', (_event, d) => select(d.id))
      .on('dblclick', (_event, d) => void expand(d.id));

    const xy = (end: string | SimNode, key: 'x' | 'y'): number => {
      if (typeof end === 'string') return 0;
      return end[key] ?? 0;
    };

    sim.on('tick', () => {
      link
        .attr('x1', (d) => xy(d.source, 'x'))
        .attr('y1', (d) => xy(d.source, 'y'))
        .attr('x2', (d) => xy(d.target, 'x'))
        .attr('y2', (d) => xy(d.target, 'y'));
      node.attr('cx', (d) => d.x ?? 0).attr('cy', (d) => d.y ?? 0);
      label.attr('x', (d) => d.x ?? 0).attr('y', (d) => d.y ?? 0);
    });

    return () => {
      sim.on('tick', null);
      sim.stop();
    };
  }, [nodes, links, highlight, select, expand]);

  return (
    <div className="graph-canvas-wrap">
      {tooLarge ? (
        <div className="graph-warn small">
          当前视图 {nodes.length} 节点,已超过 {LARGE_GRAPH_WARN}:建议用标签过滤或
          双击节点逐步展开;聚合视图将随 C 引擎接通提供。
        </div>
      ) : null}
      {nodes.length === 0 ? (
        <div className="graph-empty muted">暂无图数据:从索引队列入队,或手建第一个节点。</div>
      ) : null}
      <svg ref={svgRef} className="graph-canvas" data-node-count={nodes.length} />
    </div>
  );
}
