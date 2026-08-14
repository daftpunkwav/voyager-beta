/** 按 schema type 渲染设置控件;secret 项永不回显 value,只有配置徽标。 */

import { useEffect, useState } from 'react';
import { ServiceError } from '@/bridge/client';
import { type SettingItem, useSettingsStore } from './settingsStore';

interface FieldProps {
  item: SettingItem;
}

export function SettingField({ item }: FieldProps) {
  const setValue = useSettingsStore((s) => s.setValue);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const commit = async (value: unknown) => {
    setSaving(true);
    setError(null);
    try {
      await setValue(item.key, value);
    } catch (err) {
      const e = err as ServiceError;
      setError(e.hint ? `${e.message}(${e.hint})` : e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="setting-field">
      <div className="setting-field__head">
        <label className="setting-field__label" htmlFor={item.key}>
          {item.description || item.key}
        </label>
        {item.secret ? (
          <span
            className={`setting-badge ${item.has_value ? 'setting-badge--ok' : 'setting-badge--none'}`}
          >
            {item.has_value ? '已配置' : '未配置'}
          </span>
        ) : null}
        {saving ? <span className="small muted">保存中…</span> : null}
      </div>
      <FieldControl item={item} onCommit={commit} disabled={saving} />
      {error ? <div className="setting-field__error small">{error}</div> : null}
    </div>
  );
}

interface ControlProps {
  item: SettingItem;
  onCommit: (value: unknown) => Promise<void>;
  disabled?: boolean;
}

function FieldControl({ item, onCommit, disabled }: ControlProps) {
  switch (item.type) {
    case 'bool':
      return <BoolControl item={item} onCommit={onCommit} disabled={disabled} />;
    case 'choice':
      return <ChoiceControl item={item} onCommit={onCommit} disabled={disabled} />;
    case 'int':
    case 'float':
      return <NumberControl item={item} onCommit={onCommit} disabled={disabled} />;
    case 'json':
      return <JsonControl item={item} onCommit={onCommit} disabled={disabled} />;
    default:
      return <StrControl item={item} onCommit={onCommit} disabled={disabled} />;
  }
}

function BoolControl({ item, onCommit, disabled }: ControlProps) {
  const [checked, setChecked] = useState(Boolean(item.value));
  useEffect(() => setChecked(Boolean(item.value)), [item.value]);
  return (
    <button
      type="button"
      id={item.key}
      role="switch"
      aria-checked={checked}
      className={`switch ${checked ? 'switch--on' : ''}`}
      disabled={disabled}
      onClick={() => {
        const next = !checked;
        setChecked(next);
        void onCommit(next);
      }}
    >
      <span className="switch__knob" />
    </button>
  );
}

function ChoiceControl({ item, onCommit, disabled }: ControlProps) {
  const [value, setValue] = useState(String(item.value ?? ''));
  useEffect(() => setValue(String(item.value ?? '')), [item.value]);
  return (
    <select
      id={item.key}
      className="setting-input"
      value={value}
      disabled={disabled}
      onChange={(e) => {
        setValue(e.target.value);
        void onCommit(e.target.value);
      }}
    >
      {item.choices.map((c) => (
        <option key={c} value={c}>
          {c}
        </option>
      ))}
    </select>
  );
}

function NumberControl({ item, onCommit, disabled }: ControlProps) {
  const [text, setText] = useState(String(item.value ?? ''));
  useEffect(() => setText(String(item.value ?? '')), [item.value]);
  const flush = () => {
    if (text === String(item.value ?? '')) return;
    const num = Number(text);
    if (!Number.isFinite(num)) return; // 非法输入不提交,等用户改
    void onCommit(num);
  };
  return (
    <input
      id={item.key}
      className="setting-input"
      type="number"
      inputMode="decimal"
      value={text}
      min={item.min ?? undefined}
      max={item.max ?? undefined}
      step={item.type === 'int' ? 1 : 'any'}
      disabled={disabled}
      onChange={(e) => setText(e.target.value)}
      onBlur={flush}
    />
  );
}

function StrControl({ item, onCommit, disabled }: ControlProps) {
  // secret 项 schema 不含 value/default;输入框永远从空开始,placeholder 只提示状态
  const [text, setText] = useState(item.secret ? '' : String(item.value ?? ''));
  useEffect(() => {
    if (!item.secret) setText(String(item.value ?? ''));
  }, [item.value, item.secret]);
  const placeholder = item.secret
    ? item.has_value
      ? '已配置(输入以覆盖)'
      : '未配置'
    : String(item.value ?? '');
  const flush = () => {
    if (item.secret) {
      if (text !== '') void onCommit(text);
      setText('');
      return;
    }
    if (text !== String(item.value ?? '')) void onCommit(text);
  };
  return (
    <input
      id={item.key}
      className="setting-input"
      type={item.secret ? 'password' : 'text'}
      value={text}
      placeholder={placeholder}
      autoComplete="off"
      disabled={disabled}
      onChange={(e) => setText(e.target.value)}
      onBlur={flush}
    />
  );
}

function JsonControl({ item, onCommit, disabled }: ControlProps) {
  const [text, setText] = useState(() => JSON.stringify(item.value ?? {}, null, 2));
  const [invalid, setInvalid] = useState(false);
  useEffect(() => setText(JSON.stringify(item.value ?? {}, null, 2)), [item.value]);
  const flush = () => {
    try {
      const parsed = JSON.parse(text || '{}');
      setInvalid(false);
      void onCommit(parsed);
    } catch {
      setInvalid(true); // 红框提示,不提交
    }
  };
  return (
    <textarea
      id={item.key}
      className={`setting-input setting-input--json ${invalid ? 'setting-input--invalid' : ''}`}
      rows={5}
      value={text}
      disabled={disabled}
      onChange={(e) => {
        setText(e.target.value);
        setInvalid(false);
      }}
      onBlur={flush}
    />
  );
}
