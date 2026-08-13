import { describe, expect, it } from 'vitest';
import {
  extractBareRepoNames,
  extractGithubRepoRefs,
} from '@/utils/sessionProjectBind';

describe('extractGithubRepoRefs', () => {
  it('提取完整 GitHub URL', () => {
    const refs = extractGithubRepoRefs(
      '看看 https://github.com/openai/codex 这个仓库'
    );
    expect(refs).toEqual([
      {
        owner: 'openai',
        repo: 'codex',
        url: 'https://github.com/openai/codex',
      },
    ]);
  });

  it('提取 owner/repo', () => {
    const refs = extractGithubRepoRefs('对照 openai/codex 实现');
    expect(refs.some((r) => r.owner === 'openai' && r.repo === 'codex')).toBe(true);
  });
});

describe('extractBareRepoNames', () => {
  it('从学习源码表述提取裸名', () => {
    expect(extractBareRepoNames('我想学习一下codex的源码')).toContain('codex');
  });

  it('匹配「X 源码」', () => {
    expect(extractBareRepoNames('想读 langchain 源码')).toContain('langchain');
  });
});
