import type { GraphNode } from './types';

/** 典型浏览距离；scale = REF / dist（近大远小），并在 [MIN, MAX] 内钳制 */
export const TOOLTIP_REF_DISTANCE = 580;
/** 原 0.78 × 1.1 × 1.1 */
export const TOOLTIP_MIN_SCALE = 0.9438;
/** 原 1.06 × 1.3 × 1.1 */
export const TOOLTIP_MAX_SCALE = 1.5158;

/** 会挡住悬停卡片的 UI 浮层选择器（相对 graph-stage / 页面） */
export const GRAPH_OVERLAY_SELECTORS = [
  '.graph-toolbar',
  '.node-detail:not(.is-collapsed)',
  '.graph-statusbar',
  '.graph-hint',
  '.code-graph-sidebar',
  '.code-graph-detail',
] as const;

export interface TooltipInsets {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

export const EMPTY_TOOLTIP_INSETS: TooltipInsets = {
  left: 0,
  right: 0,
  top: 0,
  bottom: 0,
};

export function tooltipAnchorY(node: GraphNode): number {
  return node.y + Math.max(node.size, 2) * 1.1;
}

/** 视角放大（靠近）→ 信息框略大；缩小（远离）→ 略小，且限制在区间内 */
export function computeTooltipScreenScale(distance: number): number {
  if (!Number.isFinite(distance) || distance <= 0) return 1;
  const raw = TOOLTIP_REF_DISTANCE / distance;
  return Math.min(TOOLTIP_MAX_SCALE, Math.max(TOOLTIP_MIN_SCALE, raw));
}

export interface TooltipScreenLayout {
  left: number;
  top: number;
  /** 是否改到锚点下方（上方空间不足时） */
  placeBelow: boolean;
  transform: string;
}

function overlapAxis(
  a0: number,
  a1: number,
  b0: number,
  b1: number,
): number {
  return Math.max(0, Math.min(a1, b1) - Math.max(a0, b0));
}

/**
 * 根据浮层与画布的相交区域，累计左侧工具栏 / 右侧详情 / 底栏等占用的安全边距。
 */
export function accumulateOverlayInset(
  canvas: { left: number; right: number; top: number; bottom: number; width: number; height: number },
  overlay: { left: number; right: number; top: number; bottom: number; width: number; height: number },
  insets: TooltipInsets,
): void {
  const ix = overlapAxis(canvas.left, canvas.right, overlay.left, overlay.right);
  const iy = overlapAxis(canvas.top, canvas.bottom, overlay.top, overlay.bottom);
  if (ix <= 0 || iy <= 0) return;

  const midX = overlay.left + overlay.width / 2;
  const midY = overlay.top + overlay.height / 2;
  const canvasMidX = canvas.left + canvas.width / 2;
  const canvasMidY = canvas.top + canvas.height / 2;

  const isTall = iy > canvas.height * 0.28 || overlay.height >= overlay.width * 1.15;
  const isWide = ix > canvas.width * 0.28 || overlay.width >= overlay.height * 1.4;

  if (isTall && !isWide) {
    if (midX <= canvasMidX) {
      insets.left = Math.max(
        insets.left,
        Math.max(0, Math.min(overlay.right, canvas.right) - canvas.left),
      );
    } else {
      insets.right = Math.max(
        insets.right,
        Math.max(0, canvas.right - Math.max(overlay.left, canvas.left)),
      );
    }
    return;
  }

  if (isWide && midY >= canvasMidY) {
    insets.bottom = Math.max(
      insets.bottom,
      Math.max(0, canvas.bottom - Math.max(overlay.top, canvas.top)),
    );
    return;
  }

  if (isWide && midY < canvasMidY) {
    insets.top = Math.max(
      insets.top,
      Math.max(0, Math.min(overlay.bottom, canvas.bottom) - canvas.top),
    );
  }
}

/** 测量画布上遮挡浮层相对画布的 insets（像素，画布坐标系） */
export function measureGraphOverlayInsets(
  canvasEl: HTMLElement,
  selectors: readonly string[] = GRAPH_OVERLAY_SELECTORS,
): TooltipInsets {
  const canvasRect = canvasEl.getBoundingClientRect();
  const insets: TooltipInsets = { ...EMPTY_TOOLTIP_INSETS };
  const root =
    canvasEl.closest('.graph-stage, .code-graph-page, .code-graph-layout') ??
    canvasEl.ownerDocument;

  for (const sel of selectors) {
    const nodes = root.querySelectorAll(sel);
    for (const node of nodes) {
      if (!(node instanceof HTMLElement)) continue;
      if (getComputedStyle(node).display === 'none') continue;
      const r = node.getBoundingClientRect();
      if (r.width < 4 || r.height < 4) continue;
      accumulateOverlayInset(canvasRect, r, insets);
    }
  }

  return insets;
}

/**
 * 将悬停卡片摆在锚点附近，优先上方；必要时翻到下方，并钳制在「扣除浮层后」的安全区内。
 * left/top 为卡片左上角（未缩放前坐标系），配合 transform-origin: top left。
 */
export function layoutTooltipInViewport(opts: {
  anchorX: number;
  anchorY: number;
  boxW: number;
  boxH: number;
  viewW: number;
  viewH: number;
  scale: number;
  pad?: number;
  gap?: number;
  insets?: TooltipInsets;
}): TooltipScreenLayout {
  const pad = opts.pad ?? 8;
  const gap = opts.gap ?? 8;
  const scale = opts.scale;
  const w = Math.max(1, opts.boxW) * scale;
  const h = Math.max(1, opts.boxH) * scale;
  const insets = opts.insets ?? EMPTY_TOOLTIP_INSETS;

  const safeLeft = pad + insets.left;
  const safeTop = pad + insets.top;
  const safeRight = Math.max(safeLeft + w, opts.viewW - pad - insets.right);
  const safeBottom = Math.max(safeTop + h, opts.viewH - pad - insets.bottom);

  const spaceAbove = opts.anchorY - gap - h - safeTop;
  const spaceBelow = safeBottom - (opts.anchorY + gap + h);
  const placeBelow = spaceAbove < 0 && spaceBelow >= spaceAbove;

  let left = opts.anchorX - w / 2;
  let top = placeBelow ? opts.anchorY + gap : opts.anchorY - gap - h;

  /* 锚点落在左侧浮层带内：贴着安全区左缘外侧摆，避免继续居中叠到工具栏上 */
  if (opts.anchorX < safeLeft + w * 0.35) {
    left = safeLeft;
  } else if (opts.anchorX > safeRight - w * 0.35) {
    left = safeRight - w;
  }

  const maxLeft = Math.max(safeLeft, safeRight - w);
  const maxTop = Math.max(safeTop, safeBottom - h);
  left = Math.min(maxLeft, Math.max(safeLeft, left));
  top = Math.min(maxTop, Math.max(safeTop, top));

  return {
    left,
    top,
    placeBelow,
    transform: `scale(${scale.toFixed(3)})`,
  };
}
