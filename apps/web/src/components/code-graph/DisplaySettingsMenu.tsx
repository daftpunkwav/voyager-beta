/**
 * L1 图谱对比度面板 — 对齐原生引擎 DisplaySettingsMenu
 * 滑杆叠在自动密度补偿之上：1.00× = 跟随自适应
 */
import { useEffect, useRef, useState } from 'react';
import {
  DEFAULT_DISPLAY_SETTINGS,
  DISPLAY_LIMITS,
  type DisplaySettings,
} from './density';

interface DisplaySettingsMenuProps {
  settings: DisplaySettings;
  onChange: (next: DisplaySettings) => void;
}

interface SliderRowProps {
  label: string;
  hint: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}

function SliderRow({ label, hint, value, min, max, onChange }: SliderRowProps) {
  return (
    <label className="code-graph-display-menu__slider">
      <div className="code-graph-display-menu__slider-head">
        <span className="code-graph-display-menu__slider-label">{label}</span>
        <span className="code-graph-display-menu__slider-value">
          {value.toFixed(2)}×
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={0.05}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        aria-label={`${label}（${hint}）`}
      />
      <p className="code-graph-display-menu__hint">{hint}</p>
    </label>
  );
}

export function DisplaySettingsMenu({
  settings,
  onChange,
}: DisplaySettingsMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const set = (patch: Partial<DisplaySettings>) =>
    onChange({ ...settings, ...patch });

  const isDefault =
    settings.edgeBrightness === DEFAULT_DISPLAY_SETTINGS.edgeBrightness &&
    settings.nodeGlow === DEFAULT_DISPLAY_SETTINGS.nodeGlow &&
    settings.bloom === DEFAULT_DISPLAY_SETTINGS.bloom;

  return (
    <div ref={rootRef} className="code-graph-display-menu">
      <button
        type="button"
        className="code-graph-display-menu__trigger"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="dialog"
        title="对比度与亮度"
      >
        显示
        {!isDefault && <span className="code-graph-display-menu__dot" aria-hidden />}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="显示设置"
          className="code-graph-display-menu__panel glass-card glass-card--overview-inner"
        >
          <div className="code-graph-display-menu__header">
            <span className="code-graph-display-menu__title">对比度</span>
            <button
              type="button"
              className="code-graph-display-menu__reset"
              onClick={() => onChange({ ...DEFAULT_DISPLAY_SETTINGS })}
              disabled={isDefault}
            >
              重置
            </button>
          </div>

          <SliderRow
            label="边线亮度"
            hint="密图时压暗连线网"
            value={settings.edgeBrightness}
            min={DISPLAY_LIMITS.edgeBrightness.min}
            max={DISPLAY_LIMITS.edgeBrightness.max}
            onChange={(edgeBrightness) => set({ edgeBrightness })}
          />
          <SliderRow
            label="节点光晕"
            hint="单点周围的辉光增强"
            value={settings.nodeGlow}
            min={DISPLAY_LIMITS.nodeGlow.min}
            max={DISPLAY_LIMITS.nodeGlow.max}
            onChange={(nodeGlow) => set({ nodeGlow })}
          />
          <SliderRow
            label="Bloom"
            hint="整体辉光强度"
            value={settings.bloom}
            min={DISPLAY_LIMITS.bloom.min}
            max={DISPLAY_LIMITS.bloom.max}
            onChange={(bloom) => set({ bloom })}
          />

          <p className="code-graph-display-menu__footer">
            默认边线 1.20×、光晕 / Bloom 1.00×（叠在已减半的底层基础强度上）。大图洗白时继续下调。
          </p>
        </div>
      )}
    </div>
  );
}
