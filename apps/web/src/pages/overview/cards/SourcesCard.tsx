/** 资源卡:sources.list_repos 计数(就绪/导入中/失败,坑 2:计数用数组长度)。 */

import { callCapability } from '@/bridge/client';
import { useCard } from '../OverviewPage';
import { CardShell } from './CardShell';

interface RepoSummary {
  id: string;
  name: string;
  status: 'importing' | 'ready' | 'failed';
}

export function SourcesCard() {
  const card = useCard(() => callCapability<RepoSummary[]>('sources', 'list_repos'));

  const repos = card.data ?? [];
  const counts = {
    ready: repos.filter((r) => r.status === 'ready').length,
    importing: repos.filter((r) => r.status === 'importing').length,
    failed: repos.filter((r) => r.status === 'failed').length,
  };

  return (
    <CardShell
      title="资源库"
      to="/sources"
      error={card.error ? { code: (card.error as { code?: string }).code ?? 'SOURCES.UNAVAILABLE',
                            message: (card.error as Error).message } : undefined}
      onRetry={card.retry}
      loading={card.data === undefined && !card.error}
    >
      <div className="overview-nums">
        <div>
          <div className="overview-nums__value">{counts.ready}</div>
          <div className="small muted">就绪</div>
        </div>
        <div>
          <div className="overview-nums__value">{counts.importing}</div>
          <div className="small muted">导入中</div>
        </div>
        <div>
          <div className={`overview-nums__value ${counts.failed > 0 ? 'overview-nums__value--error' : ''}`}>
            {counts.failed}
          </div>
          <div className="small muted">失败</div>
        </div>
      </div>
    </CardShell>
  );
}
