import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import { TrashPanel } from '@/pages/notes/NoteTrash';

const { restoreMutate } = vi.hoisted(() => ({
  restoreMutate: vi.fn((_id: string, opts?: { onSuccess?: () => void }) => {
    opts?.onSuccess?.();
  }),
}));

vi.mock('@/hooks/useNotes', () => ({
  useTrashNotes: () => ({
    data: [{ id: 'n1', title: '已删笔记', updated_ts: 1 }],
  }),
  useRestoreNote: () => ({ mutate: restoreMutate, isPending: false }),
  usePurgeNote: () => ({ mutate: vi.fn(), isPending: false }),
  useEmptyTrash: () => ({ mutate: vi.fn(), isPending: false }),
}));

describe('回收站恢复', () => {
  it('恢复后留在回收站,不打开笔记详情', () => {
    const onClose = vi.fn();
    render(<TrashPanel open onClose={onClose} />);

    fireEvent.click(screen.getByRole('button', { name: '恢复' }));

    expect(restoreMutate).toHaveBeenCalledWith('n1', expect.any(Object));
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog', { name: '回收站' })).toBeTruthy();
  });
});
