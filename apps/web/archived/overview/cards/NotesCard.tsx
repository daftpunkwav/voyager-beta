/** 笔记卡:notes.list_notes 计数 + 最近更新 3 条。 */

import { callCapability } from '@/bridge/client';
import { useCard } from '../OverviewPage';
import { CardShell } from './CardShell';

interface NoteSummary {
  id: string;
  title: string;
  updated_ts: number;
}

export function NotesCard() {
  const card = useCard(() => callCapability<NoteSummary[]>('notes', 'list_notes', { limit: 500 }));

  const notes = card.data ?? [];
  const recent = [...notes].sort((a, b) => b.updated_ts - a.updated_ts).slice(0, 3);

  return (
    <CardShell
      title="笔记"
      to="/notes"
      error={card.error ? { code: (card.error as { code?: string }).code ?? 'NOTES.UNAVAILABLE',
                            message: (card.error as Error).message } : undefined}
      onRetry={card.retry}
      loading={card.data === undefined && !card.error}
    >
      <div className="overview-nums">
        <div>
          <div className="overview-nums__value">{notes.length}</div>
          <div className="small muted">篇笔记</div>
        </div>
      </div>
      <div className="overview-activity">
        {recent.map((n) => (
          <div key={n.id} className="overview-activity__row">{n.title}</div>
        ))}
      </div>
    </CardShell>
  );
}
