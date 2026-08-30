/** Phase-06 主题单源单测:store 与 DOM 漂移时,点一次顶栏即可切换;
 *  唯一写入走 settings.set_theme(含 system);失败不改选中态。 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

import { Topbar } from '@/components/layout/Topbar';
import { useTheme } from '@/hooks/useTheme';
import { useUIStore, type Theme } from '@/stores/uiStore';
import { applyTheme } from '@/shell/themeBridge';

beforeAll(() => {
  // jsdom 缺口:Topbar / themeBridge 读取系统深浅偏好
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
});

beforeEach(() => {
  callCapabilityMock.mockReset();
  callCapabilityMock.mockResolvedValue({});
  window.localStorage.clear(); // persist 水合不参与断言
  useUIStore.setState({ theme: 'light', toasts: [] });
  applyTheme('light');
});

function renderTopbar() {
  return render(
    <MemoryRouter>
      <Topbar />
    </MemoryRouter>,
  );
}

describe('主题单一真相(phase-06)', () => {
  it('store 说浅色但 DOM 是深色(历史双源漂移)时,点一次顶栏即切浅色并落库', async () => {
    applyTheme('dark'); // 画面是深色
    useUIStore.setState({ theme: 'light' }); // store 仍说浅色 → 修复前要点两下

    renderTopbar();
    fireEvent.click(screen.getByRole('button', { name: '切换主题' }));

    // 方向以所见(DOM)为准:发出 light,而不是 store 以为的 dark
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_theme', {
        theme: 'light',
      }),
    );
    // 落库成功后选中态与视觉一致,一次点击到位
    await waitFor(() => expect(useUIStore.getState().theme).toBe('light'));
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('changeTheme("system") 也写后端,成功后选中态与视觉跟随', async () => {
    // 顶栏只在 light↔dark 间切换;system 入口是设置页/同款 changeTheme(harness 直测)
    function Harness({ next }: { next: Theme }) {
      const { changeTheme } = useTheme();
      return (
        <button type="button" onClick={() => void changeTheme(next)}>
          go
        </button>
      );
    }
    render(
      <MemoryRouter>
        <Harness next="system" />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'go' }));

    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_theme', {
        theme: 'system',
      }),
    );
    await waitFor(() => expect(useUIStore.getState().theme).toBe('system'));
    // system 解析为当前系统偏好(jsdom mock = 浅色),data-theme 不留空
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('set_theme 失败时保持原选中态并给出 toast,不假装成功', async () => {
    callCapabilityMock.mockRejectedValue(new Error('后端服务未启动或不可达'));
    applyTheme('dark');
    useUIStore.setState({ theme: 'dark' });

    renderTopbar();
    fireEvent.click(screen.getByRole('button', { name: '切换主题' }));

    await waitFor(() => {
      const last = useUIStore.getState().toasts.at(-1);
      expect(last?.type).toBe('error');
      expect(last?.message).toContain('主题切换失败');
    });
    expect(useUIStore.getState().theme).toBe('dark');
    expect(document.documentElement.dataset.theme).toBe('dark'); // 视觉也未变
  });
});
