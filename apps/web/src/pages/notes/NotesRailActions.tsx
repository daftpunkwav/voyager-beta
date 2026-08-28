/** 笔记页主操作:人格助手与新建。首页与工作区共用同一组,靠右放置。 */

import { personaDisplayName } from '@/constants/personas';

export function NotesAssistButton({ onClick }: { onClick: () => void }) {
  const name = personaDisplayName('organizer');
  return (
    <button
      type="button"
      className="notes-rail-miyai liquid-glass liquid-glass--pill liquid-glass--green"
      aria-label={`打开 ${name}`}
      data-testid="notes-assist-btn"
      onClick={onClick}
    >
      <span className="notes-rail-miyai__orb agent-organizer" aria-hidden />
      {name}
    </button>
  );
}

export function NotesNewButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      className="btn btn-primary btn-sm notes-rail-new"
      onClick={onClick}
      data-testid="notes-new-btn"
    >
      新建
    </button>
  );
}
