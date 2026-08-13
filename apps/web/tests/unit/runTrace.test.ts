import { describe, expect, it } from 'vitest';
import {
  extractExpertThinking,
  snapshotSubagents,
  snapshotToolCalls,
} from '@/utils/runTrace';

describe('extractExpertThinking', () => {
  it('splits 【Scout】 section from hub thinking', () => {
    const full = [
      '[状态] 意图 · hub',
      '【Scout】',
      '先看目录结构',
      '再读 README',
      '【Mentor】',
      '准备讲解',
    ].join('\n');
    expect(extractExpertThinking(full, 'scout')).toContain('先看目录结构');
    expect(extractExpertThinking(full, 'scout')).not.toContain('准备讲解');
    expect(extractExpertThinking(full, 'mentor')).toContain('准备讲解');
  });
});

describe('snapshotToolCalls', () => {
  it('drops ask_user and keeps others', () => {
    const map = new Map([
      ['1', { name: 'ask_user', args: {} }],
      ['2', { name: 'dispatch_agent', args: { target_agent: 'scout' }, result: { ok: true } }],
    ]);
    const out = snapshotToolCalls(map);
    expect(out).toHaveLength(1);
    expect(out[0].name).toBe('dispatch_agent');
  });
});

describe('snapshotSubagents', () => {
  it('attaches expert thinking and marks running as ok', () => {
    const full = '【Scout】\n分析中\n';
    const out = snapshotSubagents(
      [{ agentId: 'scout', status: 'running', reason: '速览' }],
      full
    );
    expect(out[0].status).toBe('ok');
    expect(out[0].thinking).toContain('分析中');
  });

  it('prefers nested thinking/output over hub extract', () => {
    const full = '【Mentor】\n合流碎片\n';
    const out = snapshotSubagents(
      [
        {
          agentId: 'mentor',
          status: 'ok',
          thinking: '真实思考',
          output: '完整讲解正文',
        },
      ],
      full
    );
    expect(out[0].thinking).toBe('真实思考');
    expect(out[0].output).toBe('完整讲解正文');
  });

  it('can preserve running status for live stream', () => {
    const out = snapshotSubagents(
      [{ agentId: 'mentor', status: 'running', thinking: '…' }],
      '',
      { finalizeRunning: false }
    );
    expect(out[0].status).toBe('running');
  });
});
