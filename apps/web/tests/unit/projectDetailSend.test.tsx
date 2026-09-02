/** Phase-70 C 单测:ProjectDetailPage.runAgent 发送顺序(对齐 phase-68 C EmbedAgentChat)。
 *  配额 block(sendUserTurn 拒绝)时不插乐观 user / 「已发到主对话」行,仅 error toast;
 *  发送成功后才落 user + 系统两行。 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { project, sendUserTurnMock } = vi.hoisted(() => ({
  project: {
    id: 'proj1',
    name: 'octocat/hello-world',
    description: 'demo repo',
    stars: 42,
    language: 'TypeScript',
    imported_at: '2026-01-01T00:00:00Z',
    url: 'https://github.com/octocat/hello-world',
    progress: 'learning',
    tags: [],
    category_id: '',
    source: 'github',
  },
  sendUserTurnMock: vi.fn(),
}));

vi.mock('@/bridge/chatSend', () => ({
  sendUserTurn: sendUserTurnMock,
}));

vi.mock('@/hooks/useProjects', () => ({
  useProject: () => ({ data: project, isLoading: false, isError: false }),
  useProjects: () => ({ data: { items: [] } }),
  useProjectReadme: () => ({
    data: null, isLoading: false, isFetching: false, isError: false, refetch: vi.fn(),
  }),
  useCategories: () => ({ data: [] }),
  useTags: () => ({ data: [] }),
  useUpdateProgress: () => ({ mutate: vi.fn() }),
  useDeleteProject: () => ({ mutate: vi.fn() }),
  // EditProjectModal(open=false 但 hook 照常调用)需要
  useUpdateProject: () => ({ mutate: vi.fn(), isPending: false }),
  useSetProjectTags: () => ({ mutate: vi.fn(), isPending: false }),
  useCreateTag: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock('@/hooks/useNotes', () => ({
  useProjectNotes: () => ({ data: [] }),
}));

vi.mock('@/hooks/useGraph', () => ({
  useGraph: () => ({ data: null }),
}));

vi.mock('@/hooks/useCodeGraph', () => ({
  useIndexStatus: () => ({ data: null, isError: false }),
  useTriggerIndex: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteIndex: () => ({ mutate: vi.fn(), isPending: false }),
}));

import { ProjectDetailPage } from '@/pages/sources/ProjectDetailPage';
import { useUIStore } from '@/stores/uiStore';

beforeAll(() => {
  // jsdom 缺口兜底(与 embedAgentChat.test 同款)
  if (!window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
  }
  Element.prototype.scrollIntoView = () => {};
});

beforeEach(() => {
  sendUserTurnMock.mockReset();
  useUIStore.setState({ toasts: [] });
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/sources/repo/${project.id}`]}>
      <Routes>
        <Route path="/sources/repo/:id" element={<ProjectDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

/** progress=learning → 推荐 recon(Iris),hero 主按钮即「Iris 快速分析」 */
function clickRunAgent() {
  fireEvent.click(screen.getByRole('button', { name: 'Iris 快速分析' }));
}

describe('ProjectDetailPage.runAgent 发送顺序(phase-70 C)', () => {
  it('配额 block:无乐观行、无「已发到主对话」行,仅 error toast', async () => {
    sendUserTurnMock.mockRejectedValue(new Error('今日 token 配额已用完'));
    renderPage();
    clickRunAgent();

    await waitFor(() => expect(useUIStore.getState().toasts).toHaveLength(1));
    const toast = useUIStore.getState().toasts[0];
    expect(toast.type).toBe('error');
    expect(toast.message).toBe('今日 token 配额已用完');

    expect(sendUserTurnMock).toHaveBeenCalledWith(
      expect.stringContaining('请以Iris分析仓库 octocat/hello-world'),
    );
    // 不插 err 行,更无「发送成功」假阳性;切换后停在 AI 分析 tab
    expect(screen.queryByText('已发到主对话，请打开悬浮窗查看。')).not.toBeInTheDocument();
    expect(screen.queryByText(/发送失败：/)).not.toBeInTheDocument();
  });

  it('发送成功:落 user 行 + 「已发到主对话」系统行', async () => {
    sendUserTurnMock.mockResolvedValue(undefined);
    renderPage();
    clickRunAgent();

    await waitFor(() =>
      expect(screen.getByText('已发到主对话，请打开悬浮窗查看。')).toBeTruthy(),
    );
    expect(
      screen.getByText(
        `请以Iris分析仓库 ${project.name}（id=${project.id}）`,
      ),
    ).toBeTruthy();
    expect(useUIStore.getState().toasts).toHaveLength(0);
  });
});
