/**
 * 密度补偿与显示设置
 */
import { describe, expect, it } from 'vitest';
import {
  bloomIntensityScale,
  bloomIntensityScaleForGraph,
  clampDisplaySettings,
  DEFAULT_DISPLAY_SETTINGS,
  DISPLAY_LIMITS,
  edgeIntensityScale,
  nodeBoostScale,
  withStatusColorDisplay,
} from '@/components/code-graph/density';

describe('density compensation', () => {
  it('edgeIntensityScale dims ~80k edges aggressively in dark', () => {
    const s = edgeIntensityScale(78916, true);
    expect(s).toBeLessThan(0.12);
    expect(s).toBeGreaterThanOrEqual(0.025);
  });

  it('light theme keeps a higher edge floor', () => {
    const dark = edgeIntensityScale(78916, true);
    const light = edgeIntensityScale(78916, false);
    expect(light).toBeGreaterThan(dark);
    expect(light).toBeGreaterThanOrEqual(0.22);
  });

  it('keeps small graphs at full edge brightness', () => {
    expect(edgeIntensityScale(1500)).toBe(1);
  });

  it('bloom eases well before full-repo loads', () => {
    expect(bloomIntensityScale(3500)).toBe(1);
    expect(bloomIntensityScale(18448)).toBeLessThan(0.5);
  });

  it('bloomIntensityScaleForGraph further dims on huge edge counts', () => {
    const nodesOnly = bloomIntensityScale(18448);
    const withEdges = bloomIntensityScaleForGraph(18448, 78916);
    expect(withEdges).toBeLessThan(nodesOnly);
    expect(withEdges).toBeLessThan(0.35);
  });

  it('nodeBoostScale eases on dense clouds', () => {
    expect(nodeBoostScale(3500)).toBe(1);
    expect(nodeBoostScale(18448)).toBeLessThan(0.55);
  });
});

describe('display settings', () => {
  it('defaults edge 1.2x and glow/bloom UI at 1x', () => {
    expect(DEFAULT_DISPLAY_SETTINGS.edgeBrightness).toBe(1.2);
    expect(DEFAULT_DISPLAY_SETTINGS.nodeGlow).toBe(1);
    expect(DEFAULT_DISPLAY_SETTINGS.bloom).toBe(1);
    expect(DISPLAY_LIMITS.edgeBrightness.max).toBe(5);
  });

  it('exposes halved base node glow', async () => {
    const { BASE_NODE_GLOW } = await import('@/components/code-graph/density');
    expect(BASE_NODE_GLOW).toBe(0.5);
  });

  it('clamps out-of-range values', () => {
    expect(
      clampDisplaySettings({ edgeBrightness: 99, nodeGlow: -5, bloom: 1.5 }),
    ).toEqual({
      edgeBrightness: 5,
      nodeGlow: 0,
      bloom: 1.5,
    });
    expect(clampDisplaySettings({ bloom: Number.NaN }).bloom).toBe(
      DEFAULT_DISPLAY_SETTINGS.bloom,
    );
  });

  it('status coloring further reduces glow', () => {
    const next = withStatusColorDisplay({
      edgeBrightness: 1.2,
      nodeGlow: 1,
      bloom: 1,
    });
    expect(next.nodeGlow).toBeLessThan(1);
    expect(next.bloom).toBeLessThan(1);
  });
});
