import { describe, expect, it } from 'vitest';
import {
  LIGHT_EDGE_END_FACTOR,
  LIGHT_EDGE_MID_FACTOR,
  LIGHT_EDGE_WIDTH_END,
  LIGHT_EDGE_WIDTH_MID,
  computeLightEdgeDegreeFactor,
  computeLightEdgeZoomFade,
  lightEdgeAlphaAt,
  lightEdgeWidthAt,
} from '@/components/code-graph/lightEdgeStyle';
import { computeGlassDynamics } from '@/components/code-graph/nodeGlassMaterial';

describe('lightEdgeStyle', () => {
  it('中点为 61.8%，两端为 100%，差距不超过 61.8%', () => {
    expect(LIGHT_EDGE_MID_FACTOR).toBeCloseTo(0.618, 3);
    expect(LIGHT_EDGE_END_FACTOR).toBe(1);
    expect(LIGHT_EDGE_END_FACTOR - LIGHT_EDGE_MID_FACTOR).toBeLessThanOrEqual(0.618);
  });

  it('alpha 曲线：端点 1、中点 0.618', () => {
    expect(lightEdgeAlphaAt(0, false)).toBeCloseTo(1, 5);
    expect(lightEdgeAlphaAt(1, false)).toBeCloseTo(1, 5);
    expect(lightEdgeAlphaAt(0.5, false)).toBeCloseTo(0.618, 3);
    expect(lightEdgeAlphaAt(0.5, true)).toBe(1);
  });

  it('线宽：端点最粗、中点最细，差距不超过 30%', () => {
    expect(LIGHT_EDGE_WIDTH_END).toBe(1);
    expect(LIGHT_EDGE_WIDTH_MID).toBe(0.7);
    expect(LIGHT_EDGE_WIDTH_END - LIGHT_EDGE_WIDTH_MID).toBeCloseTo(0.3, 5);
    expect(lightEdgeWidthAt(0)).toBeCloseTo(1, 5);
    expect(lightEdgeWidthAt(1)).toBeCloseTo(1, 5);
    expect(lightEdgeWidthAt(0.5)).toBeCloseTo(0.7, 5);
  });

  it('远离时 zoomFade 下降，近处接近 1', () => {
    expect(computeLightEdgeZoomFade(200)).toBe(1);
    expect(computeLightEdgeZoomFade(800)).toBeLessThan(1);
    expect(computeLightEdgeZoomFade(800)).toBeGreaterThan(0.28);
    expect(computeLightEdgeZoomFade(2000)).toBe(0.28);
  });

  it('高度数节点边更淡；远离时衰减更狠', () => {
    const near = computeLightEdgeDegreeFactor(100, 0);
    const far = computeLightEdgeDegreeFactor(100, 1);
    expect(far).toBeLessThan(near);
    expect(computeLightEdgeDegreeFactor(0)).toBe(1);
  });
});

describe('computeGlassDynamics', () => {
  it('相机很远时关闭动态', () => {
    expect(computeGlassDynamics(8000, 20)).toBe(0);
  });

  it('放大靠近大节点时开启动态', () => {
    expect(computeGlassDynamics(120, 40)).toBeGreaterThan(0.5);
  });
});
