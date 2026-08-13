/** 初始相机距 target 约 800，以此为屏幕角速度基准 */
export const AUTO_ROTATE_REF_DISTANCE = 800;
export const BASE_AUTO_ROTATE_SPEED = 0.22;
export const AUTO_ROTATE_DIST_RATIO_MIN = 0.08;
export const AUTO_ROTATE_DIST_RATIO_MAX = 8;

/** 无操作多久后开始自动旋转（毫秒） */
export const IDLE_ROTATE_MS = 5_000;

/**
 * OrbitControls 的 autoRotateSpeed 为固定角速度；放大后视觉上更快。
 * 按相机距 target 的比例补偿，使屏幕上的旋转观感尽量恒定。
 */
export function computeAutoRotateSpeed(
  cameraDistance: number,
  refDistance = AUTO_ROTATE_REF_DISTANCE,
  baseSpeed = BASE_AUTO_ROTATE_SPEED,
): number {
  if (!Number.isFinite(cameraDistance) || cameraDistance <= 0) return baseSpeed;
  const ratio = Math.min(
    AUTO_ROTATE_DIST_RATIO_MAX,
    Math.max(AUTO_ROTATE_DIST_RATIO_MIN, cameraDistance / refDistance),
  );
  return baseSpeed * ratio;
}
