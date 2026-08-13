import { useEffect, useId, useRef, useState } from 'react';

export interface FilterDropdownOption {
  value: string;
  label: string;
}

interface FilterDropdownProps {
  /** 按钮前缀，如「分类：」 */
  prefix: string;
  value: string;
  options: FilterDropdownOption[];
  onChange: (value: string) => void;
  active?: boolean;
  ariaLabel: string;
}

/** 自定义筛选下拉，替代原生 select，避免深色模式下系统白底菜单 */
export function FilterDropdown({
  prefix,
  value,
  options,
  onChange,
  active = false,
  ariaLabel,
}: FilterDropdownProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  const selected = options.find((o) => o.value === value) ?? options[0];
  const displayLabel = selected ? `${prefix}${selected.label}` : prefix;

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
    <div className={`filter-dropdown${open ? ' is-open' : ''}`} ref={rootRef}>
      <button
        type="button"
        className={`filter-btn${active ? ' active' : ''}`}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((v) => !v)}
      >
        <span>{displayLabel}</span>
        <span className="chev" aria-hidden>
          ▾
        </span>
      </button>
      {open && (
        <ul className="filter-dropdown-menu" id={listId} role="listbox">
          {options.map((opt) => (
            <li key={opt.value || '__all__'} role="presentation">
              <button
                type="button"
                role="option"
                aria-selected={opt.value === value}
                className={`filter-dropdown-item${opt.value === value ? ' is-selected' : ''}`}
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
