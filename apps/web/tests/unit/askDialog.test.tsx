/** AskDialog 四种题型:渲染形态与提交值形态(字符串/数字/boolean)。 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AskDialog } from '@/pages/chat/AskDialog';
import { type PendingQuestion, useChatStore } from '@/pages/chat/chatStore';

const answerMock = vi.fn().mockResolvedValue({ matched: true });

vi.mock('@/bridge/client', () => ({
  callCapability: (...args: unknown[]) => answerMock(...args),
  ServiceError: class extends Error {},
}));

function setQuestion(q: Partial<PendingQuestion>) {
  useChatStore.setState({
    question: {
      questionId: 'q1',
      prompt: '请回答',
      kind: 'text',
      options: [],
      min: null,
      max: null,
      ...q,
    } as PendingQuestion,
  });
}

beforeEach(() => {
  answerMock.mockClear();
  useChatStore.setState({ question: null });
});

describe('AskDialog', () => {
  it('无待答问题时不渲染', () => {
    const { container } = render(<AskDialog />);
    expect(container.querySelector('.ask-mask')).toBeNull();
  });

  it('text:输入字符串提交', async () => {
    setQuestion({ kind: 'text' });
    render(<AskDialog />);
    const input = screen.getByRole('dialog').querySelector('input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '三个' } });
    fireEvent.click(screen.getByText('回答'));
    await waitFor(() =>
      expect(answerMock).toHaveBeenCalledWith('agent', 'answer_question', {
        question_id: 'q1',
        value: '三个',
      }),
    );
    expect(useChatStore.getState().question).toBeNull(); // 提交成功关闭
  });

  it('choice:选项即提交值', async () => {
    setQuestion({ kind: 'choice', options: ['方案 A', '方案 B'] });
    render(<AskDialog />);
    fireEvent.click(screen.getByText('方案 B'));
    await waitFor(() =>
      expect(answerMock).toHaveBeenCalledWith('agent', 'answer_question', {
        question_id: 'q1',
        value: '方案 B',
      }),
    );
  });

  it('slider:范围中点为默认,拖动提交数字', async () => {
    setQuestion({ kind: 'slider', min: 0, max: 100 });
    render(<AskDialog />);
    const range = screen.getByRole('dialog').querySelector(
      'input[type="range"]',
    ) as HTMLInputElement;
    expect(Number(range.value)).toBe(50); // 默认中点
    fireEvent.change(range, { target: { value: '70' } });
    fireEvent.click(screen.getByText('回答'));
    await waitFor(() =>
      expect(answerMock).toHaveBeenCalledWith('agent', 'answer_question', {
        question_id: 'q1',
        value: 70,
      }),
    );
  });

  it('confirm:确认/取消提交 boolean', async () => {
    setQuestion({ kind: 'confirm' });
    render(<AskDialog />);
    fireEvent.click(screen.getByText('取消'));
    await waitFor(() =>
      expect(answerMock).toHaveBeenCalledWith('agent', 'answer_question', {
        question_id: 'q1',
        value: false,
      }),
    );
  });
});
