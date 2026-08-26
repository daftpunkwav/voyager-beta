/** 浅色边线视觉权重：两端实、中点浅，差距 = 1 - 0.618 */
export const LIGHT_EDGE_END_FACTOR = 1;
export const LIGHT_EDGE_MID_FACTOR = 0.618;

/** 沿边 alpha：两端 1，中点 0.618（选中相关边时全程 1） */
export function lightEdgeAlphaAt(t: number, solid: boolean): number {
  if (solid) return 1;
  const s = Math.sin(Math.PI * Math.min(1, Math.max(0, t)));
  return (
    LIGHT_EDGE_END_FACTOR -
    (LIGHT_EDGE_END_FACTOR - LIGHT_EDGE_MID_FACTOR) * s
  );
}

/** 线宽：靠近节点最粗、中点最细，差距 ≤ 30% */
export const LIGHT_EDGE_WIDTH_END = 1;
export const LIGHT_EDGE_WIDTH_MID = 0.7;

export function lightEdgeWidthAt(t: number): number {
  const s = Math.sin(Math.PI * Math.min(1, Math.max(0, t)));
  return (
    LIGHT_EDGE_WIDTH_END -
    (LIGHT_EDGE_WIDTH_END - LIGHT_EDGE_WIDTH_MID) * s
  );
}

/** 视角远离时整体压暗边线，减轻密区「黑疙瘩」 */
export function computeLightEdgeZoomFade(cameraDistance: number): number {
  if (!Number.isFinite(cameraDistance) || cameraDistance <= 0) return 1;
  if (cameraDistance <= 320) return 1;
  if (cameraDistance >= 1200) return 0.28;
  const t = (cameraDistance - 320) / (1200 - 320);
  const s = t * t * (3 - 2 * t);
  return 1 - s * 0.72;
}

/** hub 度数衰减；zoomedOutBoost 越大（越远离）衰减越狠 */
export function computeLightEdgeDegreeFactor(
  degree: number,
  zoomedOutBoost = 0,
): number {
  const d = Math.max(0, degree);
  const k = 0.3 + zoomedOutBoost * 0.45;
  return 1 / (1 + Math.log2(1 + d) * k);
}
