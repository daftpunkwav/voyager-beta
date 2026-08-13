import { describe, expect, it } from 'vitest';
import {
  coalesceEmptyBodyWithThinking,
  isStatusLine,
  isStatusOnlyThinking,
  partitionThinking,
  persistableThinking,
} from '@/components/agent/StreamRenderer';

describe('partitionThinking', () => {
  it('纯执行脚手架视为 status-only', () => {
    const raw = '\n[执行] Mentor · 第 1/3 轮 · tot\n';
    expect(isStatusOnlyThinking(raw)).toBe(true);
    const { statusLines, realThinking } = partitionThinking(raw);
    expect(realThinking).toBe('');
    expect(statusLines.some((l) => l.includes('执行'))).toBe(true);
  });

  it('识别 [状态] 执行格式', () => {
    const raw = '[状态] 执行 · Mentor · 1/3\n';
    expect(isStatusOnlyThinking(raw)).toBe(true);
    expect(isStatusLine('[状态] 执行 · Mentor · 1/3')).toBe(true);
  });

  it('识别无括号的 执行 · 前缀', () => {
    expect(isStatusLine('执行 · Mentor · 第 1/3 轮 · react')).toBe(true);
  });

  it('规划脚手架 + 真路径比较 → 拆出真思考', () => {
    const raw = [
      '[规划] Mentor · tot',
      '正在生成行动计划…',
      '',
      '路径 A：类比讲解',
      '路径 B：源码走读',
      '选定：路径 A',
      '',
      '[规划完成] 开始执行…',
      '[执行] Mentor · 第 1/3 轮 · tot',
    ].join('\n');
    expect(isStatusOnlyThinking(raw)).toBe(false);
    const { realThinking, statusLines } = partitionThinking(raw);
    expect(realThinking).toContain('路径 A');
    expect(realThinking).not.toContain('[执行]');
    expect(statusLines.length).toBeGreaterThanOrEqual(3);
  });

  it('兼容「Mentor 推理中（第 n 轮）」旧回声为状态行', () => {
    expect(isStatusOnlyThinking('Mentor 推理中（第 1/3 轮 · tot）')).toBe(true);
    expect(isStatusOnlyThinking('Mentor 推理中 (第 1/3 轮 · tot)')).toBe(true);
  });

  it('单独轮次行视为状态', () => {
    expect(isStatusLine('第 1/3 轮 · tot')).toBe(true);
  });

  it('中间推理正文保留', () => {
    const raw = '[中间推理]\n用户要深度讲解，先摸底水平再展开骨架。\n';
    const { realThinking } = partitionThinking(raw);
    expect(realThinking).toContain('摸底水平');
    expect(isStatusOnlyThinking(raw)).toBe(false);
  });

  it('Hub 汇总/推理脚手架视为 status-only（不冒充思考过程）', () => {
    const raw = 'Hub 推理中 (第 1/4 轮 · plan_execute)\n[状态] Hub · 汇总中…\n';
    expect(isStatusOnlyThinking(raw)).toBe(true);
    const { realThinking } = partitionThinking(raw);
    expect(realThinking).toBe('');
  });

  it('意图识别脚手架不落库', () => {
    const raw =
      '[状态] 意图 · hub · 0.95\nHub 推理中 (第 1/4 轮 · plan_execute)\n';
    expect(persistableThinking(raw)).toBe('');
    expect(isStatusOnlyThinking(raw)).toBe(true);
  });

  it('真实规划正文可落库', () => {
    const raw = '[规划] Hub · plan_execute\n正在生成行动计划…\n\n先寒暄再问需求\n';
    expect(persistableThinking(raw)).toContain('先寒暄');
    expect(persistableThinking(raw)).not.toContain('[规划]');
  });

  it('调度说明 + 长思考 → 提升为正文', () => {
    const notice =
      '先交由 **Mentor**（深度讲解）处理：用户意图=学习 LangChain; 高置信匹配 mentor。\n\n';
    const think = Array.from(
      { length: 20 },
      (_, i) => `要点 ${i + 1}：LangChain 讲解`
    ).join('\n');
    const out = coalesceEmptyBodyWithThinking(notice, think);
    expect(out.content).toContain('要点 1');
    expect(out.content).toContain('先交由');
    expect(out.thinking).toBe('');
  });
});
