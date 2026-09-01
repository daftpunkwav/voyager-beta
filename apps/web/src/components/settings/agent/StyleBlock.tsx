import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { GlassSelect } from '@/components/common/GlassSelect';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { STYLE_KEY, STYLE_PRESETS } from './constants';
import type { SettingItem } from './types';

/** 说话风格(agent.style):全局语气叠加层,原样从 ConductBlock 搬家(phase-29) */
export function StyleBlock() {
  const addToast = useUIStore((s) => s.addToast);
  const [style, setStyle] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let alive = true;
    callCapability<SettingItem>('settings', 'get_setting', { key: STYLE_KEY })
      .then((item) => {
        if (alive) setStyle(item.value ?? item.default ?? '热心');
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const saveStyle = (value: string) => {
    const prev = style;
    setStyle(value);
    setSaving(true);
    callCapability<SettingItem>('settings', 'set_setting', { key: STYLE_KEY, value })
      .then((item) => {
        setStyle(item.value ?? value);
        addToast({ type: 'success', message: '说话风格已保存，下一轮对话生效' });
      })
      .catch((err) => {
        setStyle(prev);
        addToast({ type: 'error', message: `保存风格失败：${extractErrorMessage(err)}` });
      })
      .finally(() => setSaving(false));
  };

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">说话风格</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        全局语气叠加层，会拼进每次对话的系统提示，与各 Agent 自带气质叠加。
      </p>
      <GlassSelect
        size="sm"
        value={style ?? ''}
        options={
          loadFailed
            ? [{ value: '', label: '读取失败，请刷新重试' }]
            : [
                ...STYLE_PRESETS.map((v) => ({ value: v, label: v })),
                ...(style && !STYLE_PRESETS.includes(style)
                  ? [{ value: style, label: style }]
                  : []),
              ]
        }
        onChange={(v) => saveStyle(v)}
        aria-label="全局说话风格"
      />
      {saving && <span className="muted" style={{ fontSize: 12, marginLeft: 8 }}>保存中…</span>}
    </div>
  );
}
