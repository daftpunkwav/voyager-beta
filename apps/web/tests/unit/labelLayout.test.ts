/**
 * 图谱标签疏密度单元测试
 */
import { describe, expect, it } from 'vitest';
import {
  labelBudgetForDistance,
  labelPriority,
  labelWorldFontSize,
  pickNonOverlappingLabels,
  shortenLabelName,
} from '@/components/code-graph/labelLayout';

describe('labelLayout', () => {
  it('priority prefers hubs and file-like kinds', () => {
    const file = labelPriority({ kind: 'File', size: 8, in_calls: 2 });
    const section = labelPriority({ kind: 'Section', size: 4, in_calls: 0 });
    const hubFn = labelPriority({ kind: 'Function', size: 6, in_calls: 20 });
    expect(hubFn).toBeGreaterThan(file);
    expect(file).toBeGreaterThan(section);
  });

  it('budget shrinks when camera is far', () => {
    expect(labelBudgetForDistance(3000, 40)).toBeLessThanOrEqual(8);
    expect(labelBudgetForDistance(500, 40)).toBeGreaterThan(
      labelBudgetForDistance(2000, 40),
    );
  });

  it('world font size is capped', () => {
    expect(labelWorldFontSize(5000, 20)).toBeLessThanOrEqual(14);
    expect(labelWorldFontSize(100, 4)).toBeGreaterThanOrEqual(1.6);
  });

  it('picks non-overlapping labels by priority', () => {
    const keep = pickNonOverlappingLabels(
      [
        { id: 1, x: 0, y: 0, w: 40, h: 16, priority: 10 },
        { id: 2, x: 5, y: 2, w: 40, h: 16, priority: 100 },
        { id: 3, x: 200, y: 200, w: 40, h: 16, priority: 50 },
      ],
      2,
      4,
    );
    expect(keep.has(2)).toBe(true);
    expect(keep.has(3)).toBe(true);
    expect(keep.has(1)).toBe(false);
  });

  it('shortens quoted and path names', () => {
    expect(shortenLabelName('"python"')).toBe('python');
    expect(shortenLabelName('a/b/c.ts')).toBe('c.ts');
  });
});
