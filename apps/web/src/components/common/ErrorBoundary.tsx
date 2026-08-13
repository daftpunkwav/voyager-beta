import { Component, type ErrorInfo, type ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: (error: Error, reset: () => void) => ReactNode;
  /**
   * 外部错误上报钩子(Sentry / DataDog 等);未提供时仅 console.error
   */
  onError?: (error: Error, info: ErrorInfo) => void;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * 应用级错误边界
 *
 * - 捕获子树渲染时的同步异常,避免整页白屏
 * - 提供 fallback 渲染与 reset 重试入口
 * - onError 钩子可用于对接 Sentry / DataDog 等上报通道,未设置时仅 console.error
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  override state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // 优先调用外部 onError 上报;未提供时降级到本地 console.error
    if (this.props.onError) {
      this.props.onError(error, info);
      return;
    }
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  private readonly reset = () => {
    this.setState({ error: null });
  };

  override render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (this.props.fallback) return this.props.fallback(error, this.reset);
    return (
      <div className="app-error-fallback" role="alert" data-testid="app-error-fallback">
        <h2>页面出错了</h2>
        <p>请刷新页面或点击下方按钮重试。</p>
        <pre className="app-error-fallback__detail">{error.message}</pre>
        <button type="button" className="btn btn-primary" onClick={this.reset}>
          重试
        </button>
      </div>
    );
  }
}
