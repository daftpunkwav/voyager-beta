// @ts-nocheck
import { useEffect, useMemo, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import type { GraphNode, GraphEdge } from "./types";
import { edgeIntensityScale } from "./density";
import {
  computeLightEdgeDegreeFactor,
  computeLightEdgeZoomFade,
  lightEdgeAlphaAt,
  lightEdgeWidthAt,
} from "./lightEdgeStyle";

interface EdgeLinesProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  highlightedIds: Set<number> | null;
  opacity?: number;
  brightness?: number;
  isDark?: boolean;
  targetNodes?: GraphNode[];
}

function getClusterKey(fp?: string): string {
  if (!fp) return "";
  const parts = fp.split("/");
  return parts.slice(0, Math.min(2, parts.length)).join("/");
}

const EDGE_TYPE_COLORS: Record<string, string> = {
  CALLS: "#1DA27E",
  IMPORTS: "#3b82f6",
  DEFINES: "#a855f7",
  DEFINES_METHOD: "#a855f7",
  CONTAINS_FILE: "#22c55e",
  CONTAINS_FOLDER: "#22c55e",
  CONTAINS_PACKAGE: "#22c55e",
  HANDLES: "#eab308",
  IMPLEMENTS: "#f97316",
  HTTP_CALLS: "#e11d48",
  ASYNC_CALLS: "#ec4899",
  GRPC_CALLS: "#f59e0b",
  GRAPHQL_CALLS: "#e879f9",
  TRPC_CALLS: "#a78bfa",
  CROSS_HTTP_CALLS: "#fb923c",
  CROSS_ASYNC_CALLS: "#fb7185",
  CROSS_GRPC_CALLS: "#fbbf24",
  CROSS_GRAPHQL_CALLS: "#f0abfc",
  CROSS_TRPC_CALLS: "#c4b5fd",
  CROSS_CHANNEL: "#fdba74",
  MEMBER_OF: "#64748b",
  TESTS_FILE: "#06b6d4",
  similarity: "#2dd4bf",
  depends_on: "#fb923c",
  recommend_learn: "#f472b6",
  cross_http: "#a78bfa",
  cross_async: "#fbbf24",
  cross_channel: "#fdba74",
  cross_shared: "#94a3b8",
};

const EDGE_TYPE_COLORS_LIGHT: Record<string, string> = {
  CALLS: "#0f766e",
  IMPORTS: "#1d4ed8",
  DEFINES: "#7e22ce",
  DEFINES_METHOD: "#7e22ce",
  CONTAINS_FILE: "#15803d",
  CONTAINS_FOLDER: "#15803d",
  CONTAINS_PACKAGE: "#15803d",
  HANDLES: "#a16207",
  IMPLEMENTS: "#c2410c",
  HTTP_CALLS: "#be123c",
  ASYNC_CALLS: "#be185d",
  GRPC_CALLS: "#b45309",
  GRAPHQL_CALLS: "#a21caf",
  TRPC_CALLS: "#6d28d9",
  CROSS_HTTP_CALLS: "#c2410c",
  CROSS_ASYNC_CALLS: "#be123c",
  CROSS_GRPC_CALLS: "#a16207",
  CROSS_GRAPHQL_CALLS: "#a21caf",
  CROSS_TRPC_CALLS: "#6d28d9",
  CROSS_CHANNEL: "#c2410c",
  MEMBER_OF: "#475569",
  TESTS_FILE: "#0e7490",
  similarity: "#0d9488",
  depends_on: "#ea580c",
  recommend_learn: "#db2777",
  cross_http: "#7c3aed",
  cross_async: "#ca8a04",
  cross_channel: "#ea580c",
  cross_shared: "#64748b",
};

const DEFAULT_EDGE_COLOR = '#2dd4bf';
const DEFAULT_EDGE_COLOR_LIGHT = '#0f766e';

/* 浅色舞台偏冷灰，避免边线被洗进纯白背景 */
const BG_LIGHT = new THREE.Vector3(0.925, 0.94, 0.96);
const BG_DARK = new THREE.Vector3(0.024, 0.035, 0.059);

/** 双主题共用：视空间带宽 + 中段混向背景 + 选中提亮 */
function createEdgeRibbonMaterial(isDark: boolean) {
  return new THREE.ShaderMaterial({
    uniforms: {
      uOpacity: { value: 1 },
      uBg: { value: (isDark ? BG_DARK : BG_LIGHT).clone() },
      uResolution: { value: new THREE.Vector2(1920, 1080) },
      uPixelHalfWidth: { value: isDark ? 0.95 : 1.45 },
      uIsDark: { value: isDark ? 1 : 0 },
    },
    vertexShader: /* glsl */ `
      attribute vec3 color;
      attribute float aWeight;
      attribute float aWidth;
      attribute float aSide;
      attribute vec3 aDir;
      uniform vec2 uResolution;
      uniform float uPixelHalfWidth;
      varying vec3 vColor;
      varying float vWeight;
      varying float vSide;
      void main() {
        vColor = color;
        vWeight = aWeight;
        vSide = aSide;
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vec3 mvDir = mat3(modelViewMatrix) * aDir;
        vec3 push = cross(mvDir, mv.xyz);
        if (dot(push, push) < 1e-12) push = cross(mvDir, vec3(0.0, 1.0, 0.0));
        if (dot(push, push) < 1e-12) push = vec3(1.0, 0.0, 0.0);
        push = normalize(push);
        float resY = max(uResolution.y, 64.0);
        float halfNdc = min(uPixelHalfWidth * aWidth * 2.0 / resY, 0.012);
        float halfView = halfNdc * abs(mv.z) / max(abs(projectionMatrix[1][1]), 1e-6);
        mv.xyz += push * (aSide * halfView);
        gl_Position = projectionMatrix * mv;
      }
    `,
    fragmentShader: /* glsl */ `
      uniform float uOpacity;
      uniform vec3 uBg;
      uniform float uIsDark;
      varying vec3 vColor;
      varying float vWeight;
      varying float vSide;
      void main() {
        float w = clamp(vWeight, 0.0, 1.0);
        /* 浅色：少混背景、提高 alpha，避免连线淹没在白底里 */
        float mixAmt = uIsDark > 0.5 ? w : clamp(w * 1.15 + 0.18, 0.0, 1.0);
        vec3 col = mix(uBg, vColor, mixAmt);
        float lift = uIsDark > 0.5 ? 1.35 : 1.08;
        float add = uIsDark > 0.5 ? 0.12 : 0.02;
        col = mix(col, min(col * lift + vec3(add), vec3(1.0)), smoothstep(0.85, 1.0, w));
        if (uIsDark < 0.5) {
          col = mix(col, vColor * 0.92, 0.35);
        }
        float soft = 1.0 - smoothstep(0.35, 1.0, abs(vSide));
        float aMin = uIsDark > 0.5 ? 0.18 : 0.42;
        float aMax = uIsDark > 0.5 ? 0.92 : 0.9;
        float a = mix(aMin, aMax, w) * uOpacity * soft;
        if (a < 0.02) discard;
        gl_FragColor = vec4(col, a);
      }
    `,
    transparent: true,
    depthWrite: false,
    depthTest: true,
    /* 暗色对齐原生引擎：加法混合让连线形成星云辉光 */
    blending: isDark ? THREE.AdditiveBlending : THREE.NormalBlending,
    toneMapped: false,
    side: THREE.DoubleSide,
  });
}

export function EdgeLines({
  nodes,
  edges,
  highlightedIds,
  opacity = 1.0,
  brightness = 1.0,
  isDark = true,
  targetNodes,
}: EdgeLinesProps) {
  const edgeMat = useMemo(() => createEdgeRibbonMaterial(isDark), [isDark]);
  const { camera, controls, gl, size } = useThree();
  const fallbackTarget = useRef(new THREE.Vector3(0, 0, 0));

  const syncUniforms = (distFade = true) => {
    const pr = gl.getPixelRatio();
    const w = gl.drawingBufferWidth || size.width * pr || 1920;
    const h = gl.drawingBufferHeight || size.height * pr || 1080;
    edgeMat.uniforms.uResolution.value.set(w, h);
    edgeMat.uniforms.uBg.value.copy(isDark ? BG_DARK : BG_LIGHT);
    edgeMat.uniforms.uIsDark.value = isDark ? 1 : 0;
    if (!distFade) return;
    const target =
      controls && "target" in controls && controls.target
        ? controls.target
        : fallbackTarget.current;
    const dist = camera.position.distanceTo(target);
    /* 暗色少做远距压暗，保留 原生引擎式星云连线；浅色仍用 fade 防黑疙瘩 */
    const fade = isDark
      ? Math.max(0.72, computeLightEdgeZoomFade(dist))
      : computeLightEdgeZoomFade(dist);
    edgeMat.uniforms.uOpacity.value = Math.min(1, opacity) * fade;
  };

  useEffect(() => {
      const dense = edges.length > 12000;
    edgeMat.uniforms.uPixelHalfWidth.value = isDark
      ? dense
        ? 0.55
        : 0.85
      : dense
        ? 1.15
        : 1.55;
    syncUniforms(false);
    return () => {
      edgeMat.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [edgeMat, gl, size.width, size.height, isDark, edges.length]);

  const geometry = useMemo(() => {
    const densityScale = edgeIntensityScale(edges.length, isDark) * brightness;

    const degree = new Map();
    for (const edge of edges) {
      degree.set(edge.source, (degree.get(edge.source) || 0) + 1);
      degree.set(edge.target, (degree.get(edge.target) || 0) + 1);
    }

    const srcMap = new Map();
    for (let i = 0; i < nodes.length; i++) {
      srcMap.set(nodes[i].id, i);
    }
    const tgtArr = targetNodes ?? nodes;
    const tgtMap = targetNodes ? new Map() : srcMap;
    if (targetNodes) {
      for (let i = 0; i < targetNodes.length; i++) {
        tgtMap.set(targetNodes[i].id, i);
      }
    }

    const hasHighlight = highlightedIds && highlightedIds.size > 0;
    const palette = isDark ? EDGE_TYPE_COLORS : EDGE_TYPE_COLORS_LIGHT;
    const fallback = isDark ? DEFAULT_EDGE_COLOR : DEFAULT_EDGE_COLOR_LIGHT;
    const edgeColor = new THREE.Color();
    const brighten = new THREE.Color();

    const DIVS = 8;
    const stations = DIVS + 1;
    const vertsPerEdge = stations * 2;
    const idxPerEdge = DIVS * 6;
    const maxEdges = edges.length;
    const positions = new Float32Array(maxEdges * vertsPerEdge * 3);
    const colors = new Float32Array(maxEdges * vertsPerEdge * 3);
    const dirs = new Float32Array(maxEdges * vertsPerEdge * 3);
    const weights = new Float32Array(maxEdges * vertsPerEdge);
    const widths = new Float32Array(maxEdges * vertsPerEdge);
    const sides = new Float32Array(maxEdges * vertsPerEdge);
    const indices = new Uint32Array(maxEdges * idxPerEdge);
    let vertCount = 0;
    let idxCount = 0;

    for (const edge of edges) {
      const si = srcMap.get(edge.source);
      const ti = tgtMap.get(edge.target);
      if (si === undefined || ti === undefined) continue;

      const s = nodes[si];
      const t = tgtArr[ti];

      const sHL = !hasHighlight || highlightedIds.has(s.id);
      const tHL = !hasHighlight || highlightedIds.has(t.id);

      const sameCluster =
        getClusterKey(s.file_path) === getClusterKey(t.file_path);
      const base = sameCluster ? 1 : isDark ? 0.85 : 1.05;
      const deg =
        computeLightEdgeDegreeFactor(degree.get(s.id) || 0, 0) *
        computeLightEdgeDegreeFactor(degree.get(t.id) || 0, 0);
      let intensity = base * Math.max(isDark ? 0.55 : 0.88, deg);

      const related = hasHighlight && sHL && tHL;
      if (hasHighlight) {
        /* 选中边保持可读；其余按密度压暗（勿用 max 地板，否则 8万边仍过曝） */
        intensity = related ? 1 : (isDark ? 0.08 : 0.28) * densityScale;
      } else {
        intensity *= densityScale;
        /* 浅色再抬一档，配合默认 1.2× 亮度 */
        if (!isDark) intensity = Math.min(1.4, intensity * 1.15);
      }

      const typeKey = edge.type || edge.relation || "";
      edgeColor.set(palette[typeKey] ?? fallback);
      if (related) {
        brighten.copy(edgeColor);
        brighten.offsetHSL(0, isDark ? 0.12 : 0.18, isDark ? 0.28 : 0.38);
        const mul = isDark ? 1.25 : 1.15;
        brighten.r = Math.min(1, brighten.r * mul);
        brighten.g = Math.min(1, brighten.g * mul);
        brighten.b = Math.min(1, brighten.b * mul);
        edgeColor.copy(brighten);
      }
      const solid = related;
      const cr = edgeColor.r;
      const cg = edgeColor.g;
      const cb = edgeColor.b;

      let dx = t.x - s.x;
      let dy = t.y - s.y;
      let dz = t.z - s.z;
      const dLen = Math.hypot(dx, dy, dz) || 1;
      dx /= dLen;
      dy /= dLen;
      dz /= dLen;

      const baseVert = vertCount;
      for (let i = 0; i < stations; i++) {
        const tt = i / DIVS;
        const px = s.x + (t.x - s.x) * tt;
        const py = s.y + (t.y - s.y) * tt;
        const pz = s.z + (t.z - s.z) * tt;
        const wAlpha = lightEdgeAlphaAt(tt, solid) * intensity;
        const wWidth = lightEdgeWidthAt(tt);

        for (let side = -1; side <= 1; side += 2) {
          const o = vertCount * 3;
          positions[o] = px;
          positions[o + 1] = py;
          positions[o + 2] = pz;
          dirs[o] = dx;
          dirs[o + 1] = dy;
          dirs[o + 2] = dz;
          colors[o] = cr;
          colors[o + 1] = cg;
          colors[o + 2] = cb;
          weights[vertCount] = wAlpha;
          widths[vertCount] = wWidth;
          sides[vertCount] = side;
          vertCount++;
        }
      }

      for (let d = 0; d < DIVS; d++) {
        const i0 = baseVert + d * 2;
        indices[idxCount++] = i0;
        indices[idxCount++] = i0 + 1;
        indices[idxCount++] = i0 + 2;
        indices[idxCount++] = i0 + 1;
        indices[idxCount++] = i0 + 3;
        indices[idxCount++] = i0 + 2;
      }
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute(
      "position",
      new THREE.BufferAttribute(positions.slice(0, vertCount * 3), 3),
    );
    geo.setAttribute(
      "color",
      new THREE.BufferAttribute(colors.slice(0, vertCount * 3), 3),
    );
    geo.setAttribute(
      "aDir",
      new THREE.BufferAttribute(dirs.slice(0, vertCount * 3), 3),
    );
    geo.setAttribute(
      "aWeight",
      new THREE.BufferAttribute(weights.slice(0, vertCount), 1),
    );
    geo.setAttribute(
      "aWidth",
      new THREE.BufferAttribute(widths.slice(0, vertCount), 1),
    );
    geo.setAttribute(
      "aSide",
      new THREE.BufferAttribute(sides.slice(0, vertCount), 1),
    );
    geo.setIndex(new THREE.BufferAttribute(indices.slice(0, idxCount), 1));
    return geo;
  }, [nodes, edges, highlightedIds, targetNodes, brightness, isDark]);

  useEffect(() => {
    return () => {
      geometry.dispose();
    };
  }, [geometry]);

  useFrame(() => {
    syncUniforms(true);
  });

  return (
    <mesh
      geometry={geometry}
      material={edgeMat}
      frustumCulled={false}
      onBeforeRender={() => {
        syncUniforms(true);
      }}
    />
  );
}
