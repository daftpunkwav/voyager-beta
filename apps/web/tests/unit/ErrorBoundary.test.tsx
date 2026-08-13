import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ErrorInfo } from 'react';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';

describe('ErrorBoundary', () => {
  // 子组件抛错会让 React 内部 + ErrorBoundary 都调用 console.error;
  // 这里整体静默以避免测试输出噪声
  let consoleSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleSpy.mockRestore();
  });

  it('子组件抛错时显示默认 fallback', () => {
    function Boom(): never {
      throw new Error('boom');
    }
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>
    );
    expect(screen.getByTestId('app-error-fallback')).toBeInTheDocument();
    expect(screen.getByText('页面出错了')).toBeInTheDocument();
    expect(screen.getByText('boom')).toBeInTheDocument();
  });

  it('点击重置后恢复子树渲染', () => {
    // 闭包变量控制下次 render 是否抛错,用于验证 reset 后子树重新挂载并能正常返回
    let shouldThrow = true;
    function Toggle(): JSX.Element {
      if (shouldThrow) throw new Error('boom');
      return <span>正常内容</span>;
    }
    render(
      <ErrorBoundary>
        <Toggle />
      </ErrorBoundary>
    );
    expect(screen.getByTestId('app-error-fallback')).toBeInTheDocument();

    shouldThrow = false;
    fireEvent.click(screen.getByRole('button', { name: '重试' }));

    expect(screen.queryByTestId('app-error-fallback')).not.toBeInTheDocument();
    expect(screen.getByText('正常内容')).toBeInTheDocument();
  });

  it('提供 onError 时优先调用钩子,不再走 console.error', () => {
    const onError = vi.fn();
    function Boom(): never {
      throw new Error('boom');
    }
    render(
      <ErrorBoundary onError={onError}>
        <Boom />
      </ErrorBoundary>
    );
    expect(onError).toHaveBeenCalledTimes(1);
    // 通过类型守卫展开 mock.calls,避免使用非空断言(项目 ESLint 规则禁止)
    const firstCall = onError.mock.calls[0];
    expect(firstCall).toBeDefined();
    const [error, info] = firstCall as [Error, ErrorInfo];
    expect(error.message).toBe('boom');
    expect(info.componentStack).toEqual(expect.any(String));
    // ErrorBoundary.componentDidCatch 本体在 onError 存在时直接 return,不应再写 console
    // 但 React 内部仍会自调一次 console.error(error, componentStack) 用于错误恢复,
    // 这部分由 React 控制,与 ErrorBoundary 实现无关,因此此处不做 consoleSpy 断言。
  });
});
