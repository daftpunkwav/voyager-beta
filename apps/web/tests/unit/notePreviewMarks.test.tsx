import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';
import { flattenMultilineMarks, NOTE_PREVIEW_REMARK } from '@/pages/notes/noteMarks';

function preview(md: string) {
  return render(
    <MemoryRouter>
      <div className="preview-content">
        <MarkdownRenderer
          content={flattenMultilineMarks(md)}
          remarkPlugins={NOTE_PREVIEW_REMARK}
        />
      </div>
    </MemoryRouter>,
  );
}

describe('笔记预览底纹', () => {
  it('列表项里的加粗进 mark,不漏 ==', () => {
    const { container } = preview('1. ==cool:**学习与了解** 说明==');
    expect(container.textContent).not.toContain('==');
    const mark = container.querySelector('mark.notes-hl-cool');
    expect(mark).toBeTruthy();
    expect(mark?.querySelector('strong')?.textContent).toBe('学习与了解');
    expect(mark?.textContent).toContain('说明');
  });

  it('mark 可包住行内代码,不在反引号处拆漏 ==', () => {
    const { container } = preview('==cool:行内 `hello` 外面==');
    expect(container.textContent).not.toContain('==');
    expect(container.querySelector('mark.notes-hl-cool')).toBeTruthy();
    expect(container.querySelector('code')?.textContent).toBe('hello');
  });

  it('代码围栏里的字面 == 原样保留', () => {
    const { container } = preview('```\nconst pattern = "==a=="\n```\n');
    expect(container.textContent).toContain('const pattern = "==a=="');
    expect(container.querySelector('mark')).toBeNull();
  });

  it('围栏里误写入的架构图底纹预览仍能识别为层级图', () => {
    const md = [
      '```',
      '==rose:+-----+',
      '==rose:| 层A |',
      '==rose:+-----+',
      '==rose:| 层B |',
      '==rose:+-----+',
      '```',
    ].join('\n');
    const { container } = preview(md);
    expect(container.querySelector('.md-arch-stack')).toBeTruthy();
    expect(container.textContent).not.toContain('==rose:');
    expect(container.textContent).toContain('层A');
    expect(container.textContent).toContain('层B');
  });
});
