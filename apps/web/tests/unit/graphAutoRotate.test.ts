import { describe, expect, it } from 'vitest';
import {
  AUTO_ROTATE_REF_DISTANCE,
  BASE_AUTO_ROTATE_SPEED,
  computeAutoRotateSpeed,
} from '@/components/code-graph/graphAutoRotate';

describe('computeAutoRotateSpeed', () => {
  it('参考距离时等于基准角速度', () => {
    expect(computeAutoRotateSpeed(AUTO_ROTATE_REF_DISTANCE)).toBe(BASE_AUTO_ROTATE_SPEED);
  });

  it('放大（靠近）时降低角速度，补偿屏幕观感', () => {
    const zoomedIn = computeAutoRotateSpeed(AUTO_ROTATE_REF_DISTANCE / 4);
    expect(zoomedIn).toBeLessThan(BASE_AUTO_ROTATE_SPEED);
  });

  it('缩小（远离）时提高角速度', () => {
    const zoomedOut = computeAutoRotateSpeed(AUTO_ROTATE_REF_DISTANCE * 4);
    expect(zoomedOut).toBeGreaterThan(BASE_AUTO_ROTATE_SPEED);
  });
});
