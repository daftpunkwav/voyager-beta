/** 造人表单的能力面：不裁剪 / 指定白名单勾选。状态由 SpawnForm 持有。 */

import type { ToolItem } from './types';

interface SpawnToolFieldsProps {
  toolMode: 'all' | 'custom';
  onToolMode: (mode: 'all' | 'custom') => void;
  tools: ToolItem[];
  pickedTools: string[];
  onToggleTool: (name: string) => void;
}

export function SpawnToolFields({
  toolMode,
  onToolMode,
  tools,
  pickedTools,
  onToggleTool,
}: SpawnToolFieldsProps) {
  return (
    <div className="field-group">
      <span className="field-label">能力面</span>
      <label className="spawn-form__tool">
        <input
          type="radio"
          name="spawn-tool-mode"
          checked={toolMode === 'all'}
          onChange={() => onToolMode('all')}
        />
        不裁剪(全部工具)
      </label>
      <label className="spawn-form__tool">
        <input
          type="radio"
          name="spawn-tool-mode"
          checked={toolMode === 'custom'}
          onChange={() => onToolMode('custom')}
        />
        指定白名单
      </label>
      {toolMode === 'custom' && (
        <div className="spawn-form__tools">
          {tools.map((t) => (
            <label key={t.name} className="spawn-form__tool" title={t.description}>
              <input
                type="checkbox"
                checked={pickedTools.includes(t.name)}
                onChange={() => onToggleTool(t.name)}
              />
              <code className="mono">{t.name}</code>
            </label>
          ))}
        </div>
      )}
      <span className="field-help">
        白名单是真裁剪:没勾的工具该 subagent 真的调不了(write_file / run_shell 等含其中)。
      </span>
    </div>
  );
}
