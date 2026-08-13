import { describe, expect, it } from 'vitest';
import {
  TOOLTIP_MAX_SCALE,
  TOOLTIP_MIN_SCALE,
  TOOLTIP_REF_DISTANCE,
  accumulateOverlayInset,
  computeTooltipScreenScale,
  layoutTooltipInViewport,
} from '@/components/code-graph/graphTooltipScale';

describe('computeTooltipScreenScale', () => {
  it('靠近（放大）时钳制上限', () => {
    expect(computeTooltipScreenScale(120)).toBe(TOOLTIP_MAX_SCALE);
    expect(computeTooltipScreenScale(200)).toBe(TOOLTIP_MAX_SCALE);
  });

  it('参考距离附近接近 1', () => {
    expect(computeTooltipScreenScale(TOOLTIP_REF_DISTANCE)).toBeCloseTo(1, 5);
  });

  it('远离（缩小）时钳制下限', () => {
    expect(computeTooltipScreenScale(2000)).toBe(TOOLTIP_MIN_SCALE);
  });

  it('min/max 在上一版基础上各放大 1.1 倍', () => {
    expect(TOOLTIP_MIN_SCALE).toBeCloseTo(0.858 * 1.1, 5);
    expect(TOOLTIP_MAX_SCALE).toBeCloseTo(1.378 * 1.1, 5);
  });
});

describe('layoutTooltipInViewport', () => {
  it('上方空间不足时翻到下方', () => {
    const layout = layoutTooltipInViewport({
      anchorX: 200,
      anchorY: 20,
      boxW: 160,
      boxH: 80,
      viewW: 800,
      viewH: 600,
      scale: 1,
    });
    expect(layout.placeBelow).toBe(true);
    expect(layout.top).toBeGreaterThan(20);
  });

  it('靠近右边缘时向左钳制，避免裁切', () => {
    const layout = layoutTooltipInViewport({
      anchorX: 790,
      anchorY: 300,
      boxW: 160,
      boxH: 80,
      viewW: 800,
      viewH: 600,
      scale: 1,
      pad: 8,
    });
    expect(layout.left + 160).toBeLessThanOrEqual(800 - 8);
    expect(layout.left).toBeGreaterThanOrEqual(8);
  });

  it('左侧工具栏 insets 时不压到工具栏区域', () => {
    const layout = layoutTooltipInViewport({
      anchorX: 80,
      anchorY: 200,
      boxW: 180,
      boxH: 72,
      viewW: 800,
      viewH: 600,
      scale: 1,
      pad: 8,
      insets: { left: 236, right: 0, top: 0, bottom: 0 },
    });
    expect(layout.left).toBeGreaterThanOrEqual(236 + 8);
  });

  it('右侧详情面板 insets 时不压到右侧面板', () => {
    const layout = layoutTooltipInViewport({
      anchorX: 760,
      anchorY: 200,
      boxW: 180,
      boxH: 72,
      viewW: 800,
      viewH: 600,
      scale: 1,
      pad: 8,
      insets: { left: 0, right: 280, top: 0, bottom: 0 },
    });
    expect(layout.left + 180).toBeLessThanOrEqual(800 - 8 - 280);
  });
});

describe('accumulateOverlayInset', () => {
  it('左侧高浮层累计到 left inset', () => {
    const insets = { left: 0, right: 0, top: 0, bottom: 0 };
    accumulateOverlayInset(
      { left: 0, right: 800, top: 0, bottom: 600, width: 800, height: 600 },
      { left: 12, right: 236, top: 10, bottom: 420, width: 224, height: 410 },
      insets,
    );
    expect(insets.left).toBe(236);
    expect(insets.right).toBe(0);
  });

  it('底部状态栏累计到 bottom inset', () => {
    const insets = { left: 0, right: 0, top: 0, bottom: 0 };
    accumulateOverlayInset(
      { left: 0, right: 800, top: 0, bottom: 600, width: 800, height: 600 },
      { left: 16, right: 400, top: 552, bottom: 588, width: 384, height: 36 },
      insets,
    );
    expect(insets.bottom).toBeGreaterThan(0);
  });
});
