/* Visual density compensation for L1 graph.
 *
 * White-blob failure is dominated by additive EDGES (~80k lines crossing the
 * center). Ribbon edges + glass nodes + bloom stack harder than 原生引擎
 * thin lines, so we ease earlier and harder than 原生引擎默认值.
 *
 * Manual DisplaySettings ride ON TOP of these scales: 1.00 = auto.
 */

import { STORAGE, migrateKey } from '@/brand';

migrateKey(STORAGE.l1Display, STORAGE.legacy.l1Display);

export const EDGE_REFERENCE_COUNT = 2000;
const EDGE_MIN_SCALE = 0.025;

export function edgeIntensityScale(edgeCount: number, isDark = true): number {
  if (edgeCount <= EDGE_REFERENCE_COUNT) return 1;
  const raw = Math.pow(EDGE_REFERENCE_COUNT / edgeCount, 0.62);
  /* ?? NormalBlending ???????????????? */
  const floor = isDark ? EDGE_MIN_SCALE : 0.22;
  return Math.max(floor, raw);
}

export const NODE_REFERENCE_COUNT = 4000;
const NODE_FADE_END = 22000;
const BLOOM_FLOOR = 0.2;
const NODE_BOOST_FLOOR = 0.3;

function fadeFactor(nodeCount: number): number {
  if (nodeCount <= NODE_REFERENCE_COUNT) return 0;
  return Math.min(
    1,
    (nodeCount - NODE_REFERENCE_COUNT) / (NODE_FADE_END - NODE_REFERENCE_COUNT),
  );
}

export function bloomIntensityScale(nodeCount: number): number {
  return 1 - fadeFactor(nodeCount) * (1 - BLOOM_FLOOR);
}

export function nodeBoostScale(nodeCount: number): number {
  return 1 - fadeFactor(nodeCount) * (1 - NODE_BOOST_FLOOR);
}

/** ??+??? bloom????????? */
export function bloomIntensityScaleForGraph(
  nodeCount: number,
  edgeCount: number,
): number {
  const byNodes = bloomIntensityScale(nodeCount);
  if (edgeCount <= EDGE_REFERENCE_COUNT) return byNodes;
  const edgeFactor = Math.max(
    0.22,
    Math.pow(EDGE_REFERENCE_COUNT / edgeCount, 0.55),
  );
  return byNodes * (0.35 + 0.65 * edgeFactor);
}

const GLOW_BASE = 1.12;
const GLOW_BLUE_GAIN = 1.8;
const GLOW_RED_GAIN = 0.7;

export function nodeGlowBoost(r: number, g: number, b: number): number {
  const blueness = Math.max(0, b - Math.max(r, g));
  const redness = Math.max(0, r - Math.max(g, b));
  return GLOW_BASE + blueness * GLOW_BLUE_GAIN + redness * GLOW_RED_GAIN;
}

export interface DisplaySettings {
  /** ???????0.1�3??? 1? */
  edgeBrightness: number;
  /** ???????0�2??? 1? */
  nodeGlow: number;
  /** Bloom ???0�2??? 1? */
  bloom: number;
}

export const DEFAULT_DISPLAY_SETTINGS: DisplaySettings = {
  edgeBrightness: 1.2,
  nodeGlow: 1,
  bloom: 1,
};

export const DISPLAY_LIMITS = {
  edgeBrightness: { min: 0.1, max: 5 },
  nodeGlow: { min: 0, max: 2 },
  bloom: { min: 0, max: 2 },
} as const;

const DISPLAY_STORAGE_KEY = STORAGE.l1Display;

/** ????????????? 1.0� ?????? */
export const BASE_NODE_GLOW = 0.5;

function clampSetting(key: keyof DisplaySettings, value: unknown): number {
  const { min, max } = DISPLAY_LIMITS[key];
  const n = typeof value === 'number' ? value : Number.NaN;
  if (!Number.isFinite(n)) return DEFAULT_DISPLAY_SETTINGS[key];
  return Math.min(max, Math.max(min, n));
}

export function clampDisplaySettings(
  raw: Partial<DisplaySettings>,
): DisplaySettings {
  return {
    edgeBrightness: clampSetting('edgeBrightness', raw.edgeBrightness),
    nodeGlow: clampSetting('nodeGlow', raw.nodeGlow),
    bloom: clampSetting('bloom', raw.bloom),
  };
}

export function loadDisplaySettings(): DisplaySettings {
  try {
    const raw = localStorage.getItem(DISPLAY_STORAGE_KEY);
    if (raw) return clampDisplaySettings(JSON.parse(raw));
  } catch {
    /* ignore */
  }
  return { ...DEFAULT_DISPLAY_SETTINGS };
}

export function saveDisplaySettings(settings: DisplaySettings) {
  try {
    localStorage.setItem(DISPLAY_STORAGE_KEY, JSON.stringify(settings));
  } catch {
    /* ignore */
  }
}

/** ????????? glow??????????? */
export function withStatusColorDisplay(base: DisplaySettings): DisplaySettings {
  return {
    edgeBrightness: Math.max(0.1, base.edgeBrightness * 0.9),
    nodeGlow: Math.max(0, base.nodeGlow * 0.5),
    bloom: Math.max(0, base.bloom * 0.75),
  };
}
