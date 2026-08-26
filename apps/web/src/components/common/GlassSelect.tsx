import { useEffect, useId, useRef, useState } from 'react';

export interface GlassSelectOption {
  value: string;
  label: string;
}

interface GlassSelectProps {
  id?: string;
  value: string;
  options: GlassSelectOption[];
  onChange: (value: string) => void;
  className?: string;
  size?: 'md' | 'sm';
  'aria-label'?: string;
}

/** 表单用玻璃下拉，替代原生 select，避免深色模式下系统白底菜单 */
export function GlassSelect({
  id,
  value,
  options,
  onChange,
  className = '',
  size = 'md',
  'aria-label': ariaLabel,
}: GlassSelectProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  const selected = options.find((o) => o.value === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onEsc);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onEsc);
    };
  }, [open]);

  return (
    <div
      className={`glass-select glass-select--${size}${open ? ' is-open' : ''} ${className}`.trim()}
      ref={rootRef}
    >
      <button
        type="button"
        id={id}
        className="glass-select-trigger"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="glass-select-value">{selected?.label ?? '—'}</span>
        <span className="glass-select-chev" aria-hidden>
          ▾
        </span>
      </button>
      {open && (
        <ul className="glass-select-menu" id={listId} role="listbox">
          {options.map((opt) => (
            <li key={opt.value || '__empty__'} role="presentation">
              <button
                type="button"
                role="option"
                aria-selected={opt.value === value}
                className={`glass-select-item${opt.value === value ? ' is-selected' : ''}`}
                onClick={() => {
                  onChange(opt.value);
                  setOpen(false);
                }}
              >
                {opt.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
