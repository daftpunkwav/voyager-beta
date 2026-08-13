import { describe, expect, it } from 'vitest';
import { tryParseAsciiArchLayers } from '@/utils/asciiArch';

const SAMPLE = `
+-------------------------------------------------------+
|  CLI 层 (codex-cli/)                                   |
|  入口、参数、子命令                                     |
+-------------------------------------------------------+
|  TUI 层 (codex-tui/)                                   |
|  ratatui 终端界面                                      |
+-------------------------------------------------------+
|  Core Agent (codex-core/)  ★ 本次主线                  |
|    client/     — OpenAI 兼容 HTTP 客户端               |
|    protocol/   — 事件 + 消息 JSON 协议                 |
+-------------------------------------------------------+
|  平台抽象 (codex-linux/ macos/ windows/)               |
+-------------------------------------------------------+
`.trim();

const TABLE_SAMPLE = `
| 维度 | 内容 |
|------|------|
| 主语言 | TypeScript |
| 运行形态 | CLI + 本地 HTTP/SSE 代理 |
| 选项 | 动作 | 调度 Agent |
| 1 | 派 scout | 深挖仓库 |
`.trim();

describe('tryParseAsciiArchLayers', () => {
  it('解析中英混排 ASCII 架构图为层级', () => {
    const layers = tryParseAsciiArchLayers(SAMPLE);
    expect(layers).not.toBeNull();
    expect(layers!.length).toBeGreaterThanOrEqual(4);
    expect(layers![0]!.title).toMatch(/CLI/);
    expect(layers![0]!.lines.some((l) => l.includes('入口'))).toBe(true);
    expect(layers!.some((l) => /Core Agent/.test(l.title))).toBe(true);
  });

  it('普通代码返回 null', () => {
    const code = `pub enum Event {\n    AgentMessage,\n    TurnComplete,\n}`;
    expect(tryParseAsciiArchLayers(code)).toBeNull();
  });

  it('Markdown 管道表格不得当成架构图', () => {
    expect(tryParseAsciiArchLayers(TABLE_SAMPLE)).toBeNull();
  });
});
