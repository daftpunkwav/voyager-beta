import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { READ_ROOTS_KEY } from './constants';
import type { SettingItem } from './types';

/** 绝对路径判定:Windows 盘符(C:\ 或 C:/)、UNC(\\)、Unix(/)开头 */
function isAbsolutePath(line: string): boolean {
  return /^[A-Za-z]:[\\/]/.test(line) || line.startsWith('\\\\') || line.startsWith('/');
}

/** 只读附加根(agent.fs.read_roots,§9.9/phase-53):工作目录之外的只读白名单,下一轮读文件判定即生效 */
export function ReadRootsBlock() {
  const addToast = useUIStore((s) => s.addToast);

  const [rootsDraft, setRootsDraft] = useState('');
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    callCapability<SettingItem<string[]>>('settings', 'get_setting', { key: READ_ROOTS_KEY })
      .then((item) => {
        if (alive) setRootsDraft((item.value ?? item.default ?? []).join('\n'));
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const saveRoots = () => {
    const lines = rootsDraft
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);
    if (lines.length === 0) {
      callCapability<SettingItem<string[]>>('settings', 'set_setting', {
        key: READ_ROOTS_KEY,
        value: [],
      })
        .then(() => {
          setRootsDraft('');
          addToast({ type: 'success', message: '已清空只读附加目录，下一轮读文件判定即生效' });
        })
        .catch((err) => {
          addToast({ type: 'error', message: `保存只读附加目录失败：${extractErrorMessage(err)}` });
        });
      return;
    }
    const bad = lines.find((line) => !isAbsolutePath(line) || line.split(/[\\/]+/).includes('..'));
    if (bad) {
      addToast({
        type: 'warning',
        message: `「${bad}」不是绝对路径：一行填一个绝对路径（如 D:\\docs 或 /home/me/docs），不允许 .. 段`,
      });
      return;
    }
    callCapability<SettingItem<string[]>>('settings', 'set_setting', {
      key: READ_ROOTS_KEY,
      value: lines,
    })
      .then(() => {
        setRootsDraft(lines.join('\n'));
        addToast({ type: 'success', message: '已保存，下一轮读文件判定即生效' });
      })
      .catch((err) => {
        addToast({ type: 'error', message: `保存只读附加目录失败：${extractErrorMessage(err)}` });
      });
  };

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">只读附加目录</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        工作目录之外的只读白名单：read_file / list_dir 可访问这些目录；写入与删除仍仅限工作目录。
        保存后下一轮读文件判定即生效，无需重启。
      </p>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>读取失败请刷新。</p>
      ) : (
        <>
          <textarea
            className="field input agent-guideline-textarea"
            rows={3}
            value={rootsDraft}
            onChange={(e) => setRootsDraft(e.target.value)}
            onBlur={saveRoots}
            placeholder={'D:\\docs\n/home/me/docs'}
            aria-label="只读附加目录"
          />
          <div className="agent-guideline-meta">
            <span className="muted">{rootsDraft.split('\n').filter((s) => s.trim()).length} 个目录</span>
            <button type="button" className="btn btn-sm btn-ghost" onClick={saveRoots}>
              保存
            </button>
          </div>
        </>
      )}
    </div>
  );
}
