import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import {
  CONFIRM_MESSAGES,
  fmtTs,
  fmtValue,
  RETENTION_KEY,
  RETENTION_MAX,
  ZONE_LABELS,
} from './constants';
import type { MemorySnapshot, MemoryZone, SettingItem } from './types';

/** 记忆区:摘要/键值/情节/语义/工作/保留天数/清空 */
export function MemoryBlock() {
  const addToast = useUIStore((s) => s.addToast);
  const [mem, setMem] = useState<MemorySnapshot | null>(null);
  const [memLoadFailed, setMemLoadFailed] = useState(false);
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [retention, setRetention] = useState('');
  const [confirmZone, setConfirmZone] = useState<MemoryZone | null>(null);
  const [clearing, setClearing] = useState(false);
  const [busyZone, setBusyZone] = useState<MemoryZone | null>(null);

  const reload = () =>
    callCapability<MemorySnapshot>('agent', 'get_memory', {})
      .then((snap) => setMem(snap))
      .catch((err) => {
        addToast({ type: 'error', message: `记忆快照刷新失败：${extractErrorMessage(err)}` });
      });

  useEffect(() => {
    let alive = true;
    callCapability<MemorySnapshot>('agent', 'get_memory', {})
      .then((snap) => {
        if (!alive) return;
        setMem(snap);
        setRetention((prev) => (prev === '' ? String(snap.retention_days) : prev));
      })
      .catch((err) => {
        if (!alive) return;
        setMemLoadFailed(true);
        addToast({ type: 'error', message: `记忆快照加载失败：${extractErrorMessage(err)}` });
      });
    callCapability<SettingItem<number>>('settings', 'get_setting', { key: RETENTION_KEY })
      .then((item) => {
        if (alive) setRetention(String(item.value ?? item.default ?? 0));
      })
      .catch(() => {
        /* 保留天数读取失败由快照值兜底,不拦记忆区 */
      });
    return () => {
      alive = false;
    };
  }, []);

  const addProfile = async () => {
    const key = newKey.trim();
    if (!key) {
      addToast({ type: 'warning', message: '请先填写画像键' });
      return;
    }
    try {
      await callCapability('agent', 'set_profile', { key, value: newValue });
      setNewKey('');
      setNewValue('');
      addToast({ type: 'success', message: '画像键值已保存' });
      await reload();
    } catch (err) {
      addToast({ type: 'error', message: `保存画像失败：${extractErrorMessage(err)}` });
    }
  };

  const deleteProfile = async (key: string) => {
    try {
      await callCapability('agent', 'delete_profile', { key });
      addToast({ type: 'success', message: `已删除画像键「${key}」` });
      await reload();
    } catch (err) {
      addToast({ type: 'error', message: `删除画像失败：${extractErrorMessage(err)}` });
    }
  };

  const clearWorking = async () => {
    setBusyZone('working');
    try {
      await callCapability('agent', 'clear_memory', { zone: 'working' });
      addToast({ type: 'success', message: '工作记忆已清空' });
      await reload();
    } catch (err) {
      addToast({ type: 'error', message: `清空失败：${extractErrorMessage(err)}` });
    } finally {
      setBusyZone(null);
    }
  };

  const clearMemory = async () => {
    const zone = confirmZone;
    if (!zone || zone === 'working') return;
    setClearing(true);
    try {
      await callCapability('agent', 'clear_memory', { zone });
      addToast({ type: 'success', message: `已清空${ZONE_LABELS[zone]}` });
      await reload();
    } catch (err) {
      addToast({ type: 'error', message: `清空失败：${extractErrorMessage(err)}` });
    } finally {
      setClearing(false);
      setConfirmZone(null);
    }
  };

  const saveRetention = () => {
    const n = Number(retention);
    if (!Number.isInteger(n) || n < 0 || n > RETENTION_MAX) {
      addToast({ type: 'warning', message: `保留天数须为 0–${RETENTION_MAX} 的整数，0 表示交给 Agent 管理` });
      return;
    }
    callCapability<SettingItem<number>>('settings', 'set_setting', { key: RETENTION_KEY, value: n })
      .then(() => {
        addToast({
          type: 'success',
          message:
            n > 0
              ? `情节记忆保留 ${n} 天，打开本页时清理更早情节`
              : '已交给 Agent 管理，不再按天清理',
        });
      })
      .catch((err) => {
        addToast({ type: 'error', message: `保存保留天数失败：${extractErrorMessage(err)}` });
      });
  };

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">记忆</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
        Agent 的四类记忆。画像摘要会注入每次对话的系统提示；清空只影响记忆，
        对话时间线、笔记与项目保留。
      </p>
      {memLoadFailed && (
        <p className="muted" style={{ fontSize: 12 }}>
          记忆快照加载失败，上方风格与准则不受影响；请刷新重试。
        </p>
      )}
      {!memLoadFailed && !mem && (
        <p className="muted" style={{ fontSize: 12 }}>记忆快照加载中…</p>
      )}
      {mem && (
        <>
          <div className="memory-subhead">画像摘要</div>
          <pre className="memory-summary">{mem.profile.summary}</pre>

          <div className="memory-subhead">画像键值</div>
          {mem.profile.items.length === 0 ? (
            <p className="muted" style={{ fontSize: 12 }}>暂无画像键值。</p>
          ) : (
            <ul className="memory-kv-list">
              {mem.profile.items.map((item) => (
                <li key={item.key} className="memory-kv-row">
                  <span className="memory-kv-key">{item.key}</span>
                  <span className="memory-kv-value">{fmtValue(item.value)}</span>
                  <button
                    type="button"
                    className="btn btn-sm btn-ghost"
                    onClick={() => void deleteProfile(item.key)}
                  >
                    删除
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="memory-form-row">
            <input
              className="field input"
              style={{ maxWidth: 180 }}
              placeholder="键，如 学习目标"
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              aria-label="新画像键"
            />
            <input
              className="field input"
              placeholder="值"
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              aria-label="新画像值"
            />
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => void addProfile()}>
              添加
            </button>
          </div>

          <div className="memory-subhead">情节记忆（最近 {mem.episodic.shown} 条）</div>
          {mem.episodic.shown === 0 ? (
            <p className="muted" style={{ fontSize: 12 }}>暂无情节记录。</p>
          ) : (
            <ul className="memory-entry-list">
              {mem.episodic.recent.map((e) => (
                <li key={e.id} className="memory-entry">
                  <time>{fmtTs(e.ts)}</time>
                  <span className="memory-kind">{e.kind}</span>
                  <span className="memory-entry-summary">{e.summary}</span>
                </li>
              ))}
            </ul>
          )}

          <div className="memory-subhead">语义记忆（最近 {mem.semantic.shown} 条）</div>
          {mem.semantic.shown === 0 ? (
            <p className="muted" style={{ fontSize: 12 }}>暂无沉淀的事实。</p>
          ) : (
            <ul className="memory-entry-list">
              {mem.semantic.recent.map((f) => (
                <li key={f.id} className="memory-entry">
                  <time>{fmtTs(f.ts)}</time>
                  <span className="memory-entry-summary">
                    {f.subject} · {f.relation} · {f.object}
                  </span>
                </li>
              ))}
            </ul>
          )}

          <div className="memory-subhead">工作记忆</div>
          <div className="memory-form-row">
            <span className="muted" style={{ fontSize: 12 }}>
              当前 {mem.working.size} 条 · 进程内，重启即空
            </span>
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={() => void clearWorking()}
              disabled={busyZone === 'working'}
            >
              清空
            </button>
          </div>

          <div className="memory-subhead">情节保留天数</div>
          <div className="memory-form-row">
            <input
              className="field input"
              type="number"
              min={0}
              max={RETENTION_MAX}
              style={{ maxWidth: 120 }}
              value={retention}
              onChange={(e) => setRetention(e.target.value)}
              onBlur={saveRetention}
              aria-label="情节记忆保留天数"
            />
            <button type="button" className="btn btn-sm btn-ghost" onClick={saveRetention}>
              保存
            </button>
          </div>
          <p className="muted" style={{ fontSize: 12 }}>
            0 = 不按天自动清（交给 Agent 管理）；大于 0 = 打开本页时清理超过天数的情节。
          </p>

          <div className="memory-subhead">清空记忆</div>
          <div className="memory-zone-grid">
            {(['profile', 'episodic', 'semantic'] as const).map((z) => (
              <button
                key={z}
                type="button"
                className="btn btn-sm btn-danger"
                onClick={() => setConfirmZone(z)}
              >
                清空{ZONE_LABELS[z]}
              </button>
            ))}
            <button
              type="button"
              className="btn btn-sm btn-danger"
              onClick={() => setConfirmZone('all')}
              data-testid="clear-memory-all-btn"
            >
              清空全部
            </button>
          </div>
        </>
      )}

      {confirmZone && confirmZone !== 'working' && (
        <ConfirmDialog
          open
          title={`清空${ZONE_LABELS[confirmZone]}`}
          message={CONFIRM_MESSAGES[confirmZone]}
          confirmLabel="清空"
          danger
          onConfirm={() => void clearMemory()}
          onCancel={() => setConfirmZone(null)}
        />
      )}
    </div>
  );
}
