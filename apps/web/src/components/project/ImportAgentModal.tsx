import type { ReactNode } from 'react';

interface ImportAgentModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  size?: 'default' | 'large';
  children: ReactNode;
  /** Agent 面板；不可用时可省略以折叠右侧 */
  agentPanel?: ReactNode;
}

/** 导入 / 同步弹窗：左侧业务区 : 右侧 Agent = 1.168 : 1 */
export function ImportAgentModal({
  open,
  onClose,
  title,
  subtitle,
  size = 'default',
  children,
  agentPanel,
}: ImportAgentModalProps) {
  if (!open) return null;

  return (
    <div className="modal-overlay import-modal-overlay" role="presentation" onClick={onClose}>
      <div
        className={`import-agent-modal glass-card glass-card--dialog ${size === 'large' ? 'import-agent-modal--large' : ''}${!agentPanel ? ' import-agent-modal--no-agent' : ''}`}
        role="dialog"
        aria-labelledby="import-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="import-agent-modal__header">
          <div>
            <h2 id="import-modal-title">{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button type="button" className="chat-icon-btn" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </header>
        <div className="import-agent-modal__body">
          <div className="import-agent-modal__biz">{children}</div>
          {agentPanel && <div className="import-agent-modal__agent">{agentPanel}</div>}
        </div>
      </div>
    </div>
  );
}
