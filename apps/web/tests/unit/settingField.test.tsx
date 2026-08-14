/** SettingField 控件映射:各 type 渲染正确控件;secret 项永不回显 value。 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { SettingField } from '@/pages/settings/SettingField';
import { useSettingsStore, type SettingItem } from '@/pages/settings/settingsStore';

vi.mock('@/bridge/client', () => ({
  callCapability: vi.fn(),
  ServiceError: class extends Error {},
}));

function setItem(partial: Partial<SettingItem>): SettingItem {
  return {
    key: 'test.key',
    module: 'test',
    type: 'str',
    description: '测试项',
    secret: false,
    choices: [],
    min: null,
    max: null,
    has_value: false,
    ...partial,
  } as SettingItem;
}

function setItems(items: SettingItem[]) {
  useSettingsStore.setState({ items, error: null, loading: false });
}

let setValueMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  setValueMock = vi.fn().mockResolvedValue(undefined);
  useSettingsStore.setState({
    items: [],
    error: null,
    loading: false,
    setValue: setValueMock,
  } as never);
});

describe('SettingField 控件映射', () => {
  it('bool → switch,点击即提交取反值', () => {
    setItems([setItem({ type: 'bool', value: false })]);
    const { container } = render(<SettingField item={useSettingsStore.getState().items[0]} />);
    const sw = container.querySelector('[role="switch"]') as HTMLElement;
    expect(sw.getAttribute('aria-checked')).toBe('false');
    fireEvent.click(sw);
    expect(setValueMock).toHaveBeenCalledWith('test.key', true);
  });

  it('choice → select,选项只来自 schema choices', () => {
    setItems([setItem({ type: 'choice', choices: ['dark', 'light'], value: 'dark' })]);
    render(<SettingField item={useSettingsStore.getState().items[0]} />);
    const sel = screen.getByLabelText('测试项') as HTMLSelectElement;
    expect(sel.value).toBe('dark');
    expect(sel.options).toHaveLength(2); // 不给自由输入
    fireEvent.change(sel, { target: { value: 'light' } });
    expect(setValueMock).toHaveBeenCalledWith('test.key', 'light');
  });

  it('int → number input,失焦提交数值', () => {
    setItems([setItem({ type: 'int', value: 5, min: 1, max: 10 })]);
    render(<SettingField item={useSettingsStore.getState().items[0]} />);
    const input = screen.getByLabelText('测试项') as HTMLInputElement;
    expect(input.type).toBe('number');
    fireEvent.change(input, { target: { value: '8' } });
    fireEvent.blur(input);
    expect(setValueMock).toHaveBeenCalledWith('test.key', 8);
  });

  it('str → text input,失焦且变化才提交', () => {
    setItems([setItem({ type: 'str', value: 'JetBrains Mono' })]);
    render(<SettingField item={useSettingsStore.getState().items[0]} />);
    const input = screen.getByLabelText('测试项') as HTMLInputElement;
    expect(input.type).toBe('text');
    fireEvent.blur(input); // 未变化不提交
    expect(setValueMock).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: 'Sarasa Mono SC' } });
    fireEvent.blur(input);
    expect(setValueMock).toHaveBeenCalledWith('test.key', 'Sarasa Mono SC');
  });

  it('json → textarea,非法 JSON 不提交', () => {
    setItems([setItem({ type: 'json', value: { a: 1 } })]);
    render(<SettingField item={useSettingsStore.getState().items[0]} />);
    const ta = screen.getByLabelText('测试项') as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: '{bad' } });
    fireEvent.blur(ta);
    expect(setValueMock).not.toHaveBeenCalled();
    fireEvent.change(ta, { target: { value: '{"a": 2}' } });
    fireEvent.blur(ta);
    expect(setValueMock).toHaveBeenCalledWith('test.key', { a: 2 });
  });
});

describe('secret 语义', () => {
  it('secret → password 输入,value 永不出现在 DOM', () => {
    setItems([setItem({ type: 'str', secret: true, has_value: true })]);
    render(<SettingField item={useSettingsStore.getState().items[0]} />);
    const input = screen.getByLabelText('测试项') as HTMLInputElement;
    expect(input.type).toBe('password');
    expect(input.value).toBe(''); // 不回显
    expect(input.placeholder).toBe('已配置(输入以覆盖)');
    expect(screen.getByText('已配置')).toBeTruthy(); // 徽标基于 has_value
    fireEvent.change(input, { target: { value: 'sk-new' } });
    fireEvent.blur(input);
    expect(setValueMock).toHaveBeenCalledWith('test.key', 'sk-new');
    expect(input.value).toBe(''); // 提交后清空,不留痕
  });

  it('secret 未配置 → 徽标"未配置",placeholder 无值提示', () => {
    setItems([setItem({ type: 'str', secret: true, has_value: false })]);
    render(<SettingField item={useSettingsStore.getState().items[0]} />);
    expect(screen.getByText('未配置')).toBeTruthy();
    expect((screen.getByLabelText('测试项') as HTMLInputElement).placeholder).toBe('未配置');
  });
});
