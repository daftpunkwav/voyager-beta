import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { WORKDIR_KEY } from './constants';
import type { SettingItem } from './types';

/** 工作目录(agent.workspace.dir,§9.10):相对仓库根,保存后需重启才切换 jail */
export function WorkspaceBlock() {
  const addToast = useUIStore((s) => s.addToast);

  const [workdir, setWorkdir] = useState('');
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    callCapability<SettingItem<string>>('settings', 'get_setting', { key: WORKDIR_KEY })
      .then((item) => {
        if (alive) setWorkdir(item.value ?? item.default ?? '');
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const saveWorkdir = () => {
    const next = workdir.trim();
    if (next.split(/[\\/]+/).includes('..')) {
      addToast({ type: 'warning', message: '工作目录不允许包含 .. 段' });
      return;
    }
    callCapability<SettingItem<string>>('settings', 'set_setting', { key: WORKDIR_KEY, value: next })
      .then(() => {
        setWorkdir(next);
        addToast({ type: 'success', message: '已保存。重启开发服务后，文件工具与资源库会用新目录。' });
      })
      .catch((err) => {
        addToast({ type: 'error', message: `保存工作目录失败：${extractErrorMessage(err)}` });
      });
  };

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">工作目录</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        相对仓库根，默认 workspace；与资源库共用。保存后需重启开发服务才切换。
      </p>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>读取失败请刷新。</p>
      ) : (
        <div className="memory-form-row">
          <input
            className="field input"
            style={{ maxWidth: 260 }}
            value={workdir}
            onChange={(e) => setWorkdir(e.target.value)}
            onBlur={saveWorkdir}
            placeholder="workspace"
            aria-label="工作目录"
          />
          <button type="button" className="btn btn-sm btn-ghost" onClick={saveWorkdir}>
            保存
          </button>
        </div>
      )}
    </div>
  );
}
