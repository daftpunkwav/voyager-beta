/**
 * L0 布局：相对秩圆心、树状层距、径向铺满
 */
import { describe, expect, it } from 'vitest';
import {
  clusterRadius,
  coarsenClustersForDisplay,
  fallbackCommunities,
  filledDiskRadius,
  forceLayout3d,
  foundationRadius,
  hubnessRadius,
  layoutEdgeWeight,
  radialLayout3d,
  relativeRankHigh,
  targetDisplayClusters,
  treeClusterOrderY,
  treeLayout3d,
  treeRingRadius,
} from '@/components/graph/l0Layout3d';

type Vec = {
  id: string;
  x: number;
  y: number;
  z: number;
  size: number;
  foundation: number;
  hubness: number;
  clusterId: string;
  fineClusterId: string;
  stars: number;
};

function makeVec(
  id: string,
  clusterId: string,
  foundation: number,
  hubness: number,
  fineClusterId = clusterId,
): Vec {
  return {
    id,
    x: 0,
    y: 0,
    z: 0,
    size: 3,
    foundation,
    hubness,
    clusterId,
    fineClusterId,
    stars: 100,
  };
}

describe('relative rank and filled disk', () => {
  it('ranks higher values closer to 1', () => {
    const r = relativeRankHigh([0.1, 0.9, 0.5]);
    expect(r[1]).toBe(1);
    expect(r[0]).toBe(0);
    expect(r[2]).toBe(0.5);
  });

  it('filledDiskRadius: higher centrality closer to center', () => {
    expect(filledDiskRadius(100, 1)).toBeLessThan(filledDiskRadius(100, 0));
    expect(filledDiskRadius(100, 1)).toBeLessThan(25);
  });

  it('targets a bounded number of display clusters', () => {
    expect(targetDisplayClusters(232)).toBeLessThanOrEqual(10);
  });

  it('coarsens many tiny clusters into target count', () => {
    const cluster = new Map<string, string>();
    const links: { source: string; target: string; w: number }[] = [];
    for (let i = 0; i < 40; i += 1) {
      cluster.set(`n${i}`, `c${i}`);
      if (i > 0) links.push({ source: `n${i - 1}`, target: `n${i}`, w: 0.4 });
    }
    const coarse = coarsenClustersForDisplay(cluster, links, 8);
    expect(new Set(coarse.values()).size).toBeLessThanOrEqual(8);
  });

  it('layoutEdgeWeight lifts weak edges', () => {
    expect(layoutEdgeWeight(0.1)).toBeGreaterThan(0.1);
  });
});

describe('l0 layout metrics', () => {
  it('clusterRadius grows with member count', () => {
    expect(clusterRadius(100)).toBeGreaterThan(clusterRadius(5));
  });

  it('foundationRadius / treeRingRadius follow centrality', () => {
    expect(foundationRadius(100, 0.9)).toBeLessThan(foundationRadius(100, 0.2));
    expect(treeRingRadius(100, 0.9, 8)).toBeLessThan(treeRingRadius(100, 0.1, 8));
  });

  it('hubnessRadius: higher hubness → closer to center', () => {
    expect(hubnessRadius(200, 1)).toBeLessThan(hubnessRadius(200, 0));
  });
});

describe('l0 tree layout', () => {
  it('puts smaller layers above larger ones (higher Y)', () => {
    const nodes = [
      makeVec('a1', 'small', 0.8, 0.5),
      makeVec('a2', 'small', 0.3, 0.4),
      makeVec('a3', 'small', 0.2, 0.3),
      ...Array.from({ length: 8 }, (_, i) => makeVec(`b${i}`, 'large', 0.5, 0.4)),
      ...Array.from({ length: 4 }, (_, i) => makeVec(`m${i}`, 'mid', 0.5, 0.4)),
    ];
    treeLayout3d(nodes, []);
    const order = treeClusterOrderY(nodes);
    const sizes = order.map(
      (id) => nodes.filter((n) => n.clusterId === id).length,
    );
    expect(sizes[0]!).toBeGreaterThanOrEqual(sizes[sizes.length - 1]!);
    const topY = nodes
      .filter((n) => n.clusterId === order[order.length - 1])
      .reduce((s, n) => s + n.y, 0);
    const botY = nodes
      .filter((n) => n.clusterId === order[0])
      .reduce((s, n) => s + n.y, 0);
    expect(topY).toBeGreaterThan(botY);
  });

  it('balances layers but keeps small-top large-bottom gradient', () => {
    const nodes = [
      ...Array.from({ length: 5 }, (_, i) => makeVec(`s${i}`, 'tiny', 0.4, 0.3)),
      ...Array.from({ length: 180 }, (_, i) =>
        makeVec(`b${i}`, 'huge', 0.3 + (i % 10) / 20, 0.4, `f${i % 12}`),
      ),
    ];
    treeLayout3d(nodes, []);
    const order = treeClusterOrderY(nodes);
    const sizes = order.map(
      (id) => nodes.filter((n) => n.clusterId === id).length,
    );
    expect(sizes[0]!).toBeGreaterThanOrEqual(sizes[sizes.length - 1]!);
    expect(sizes[0]! / Math.max(1, sizes[sizes.length - 1]!)).toBeGreaterThan(1.5);
  });

  it('uses compact vertical gaps (~1.5x of prior tight gap)', () => {
    const nodes = [
      ...Array.from({ length: 12 }, (_, i) => makeVec(`a${i}`, 'c12', 0.5, 0.4, `f${i % 3}`)),
      ...Array.from({ length: 20 }, (_, i) => makeVec(`b${i}`, 'c20', 0.5, 0.4, `f${i % 4}`)),
      ...Array.from({ length: 28 }, (_, i) => makeVec(`c${i}`, 'c28', 0.5, 0.4, `f${i % 5}`)),
    ];
    treeLayout3d(nodes, []);
    const ys = [...new Set(nodes.map((n) => n.clusterId))].map((cid) => {
      const ms = nodes.filter((n) => n.clusterId === cid);
      return ms.reduce((s, n) => s + n.y, 0) / ms.length;
    });
    const span = Math.max(...ys) - Math.min(...ys);
    expect(span).toBeLessThan(360);
  });
});

describe('l0 radial layout', () => {
  it('places highest relative hubness nearest origin', () => {
    const nodes = [
      makeVec('hub', 'c1', 0.5, 0.95),
      makeVec('leaf', 'c1', 0.2, 0.05),
      makeVec('mid', 'c2', 0.4, 0.5),
    ];
    radialLayout3d(nodes, []);
    const dist = (n: Vec) => Math.hypot(n.x, n.z);
    expect(dist(nodes.find((n) => n.id === 'hub')!)).toBeLessThan(
      dist(nodes.find((n) => n.id === 'leaf')!),
    );
  });

  it('fills mid-disk for ~200 nodes instead of hollow ring', () => {
    const nodes = Array.from({ length: 200 }, (_, i) =>
      makeVec(`n${i}`, `c${i % 8}`, 0.4, i / 199, `f${i % 20}`),
    );
    radialLayout3d(nodes, []);
    const maxR = Math.max(...nodes.map((n) => Math.hypot(n.x, n.z)));
    const midCount = nodes.filter((n) => {
      const r = Math.hypot(n.x, n.z);
      return r > maxR * 0.15 && r < maxR * 0.75;
    }).length;
    expect(midCount).toBeGreaterThan(60);
    expect(Math.min(...nodes.map((n) => Math.hypot(n.x, n.z)))).toBeLessThan(maxR * 0.25);
  });
});

describe('l0 force layout', () => {
  it('keeps higher relative foundation nearer cluster centroid', () => {
    const nodes = [
      makeVec('core', 'g', 0.95, 0.6),
      makeVec('app1', 'g', 0.15, 0.3, 'g2'),
      makeVec('app2', 'g', 0.2, 0.25, 'g2'),
      makeVec('other', 'h', 0.5, 0.4),
      makeVec('other2', 'h', 0.4, 0.35),
    ];
    const links = [
      { source: 'core', target: 'app1', w: 0.8 },
      { source: 'core', target: 'app2', w: 0.75 },
      { source: 'app1', target: 'app2', w: 0.5 },
      { source: 'other', target: 'other2', w: 0.7 },
    ];
    forceLayout3d(nodes, links, 40);
    const g = nodes.filter((n) => n.clusterId === 'g');
    const cx = g.reduce((s, n) => s + n.x, 0) / g.length;
    const cy = g.reduce((s, n) => s + n.y, 0) / g.length;
    const cz = g.reduce((s, n) => s + n.z, 0) / g.length;
    const d = (n: Vec) => Math.hypot(n.x - cx, n.y - cy, n.z - cz);
    expect(d(nodes.find((n) => n.id === 'core')!)).toBeLessThan(
      d(nodes.find((n) => n.id === 'app1')!),
    );
  });
});

describe('fallbackCommunities', () => {
  it('merges strong edges', () => {
    const m = fallbackCommunities(
      ['a', 'b', 'c', 'd'],
      [
        { source: 'a', target: 'b', w: 0.9 },
        { source: 'b', target: 'c', w: 0.85 },
        { source: 'd', target: 'a', w: 0.1 },
      ],
    );
    expect(m.get('a')).toBe(m.get('b'));
    expect(m.get('b')).toBe(m.get('c'));
  });
});
