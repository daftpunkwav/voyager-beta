/** 任务卡:graph.list_index_jobs 的队列状态计数(进行中线)。 */

import { callCapability } from '@/bridge/client';
import { useCard } from '../OverviewPage';
import { CardShell } from './CardShell';

interface IndexJob {
  id: string;
  project: string;
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled';
  error: string;
}

export function TasksCard() {
  const card = useCard(() => callCapability<IndexJob[]>('graph', 'list_index_jobs'));

  const jobs = card.data ?? [];
  const counts = {
    running: jobs.filter((j) => j.status === 'running').length,
    queued: jobs.filter((j) => j.status === 'queued').length,
    failed: jobs.filter((j) => j.status === 'failed').length,
    done: jobs.filter((j) => j.status === 'done').length,
  };

  return (
    <CardShell
      title="索引任务"
      to="/graph"
      error={card.error ? { code: (card.error as { code?: string }).code ?? 'GRAPH.UNAVAILABLE',
                            message: (card.error as Error).message } : undefined}
      onRetry={card.retry}
      loading={card.data === undefined && !card.error}
    >
      {jobs.length === 0 && !card.error ? (
        <div className="small muted">队列为空:入队一个仓库开始建图。</div>
      ) : (
        <>
          <div className="overview-nums">
            <div>
              <div className="overview-nums__value">{counts.running}</div>
              <div className="small muted">索引中</div>
            </div>
            <div>
              <div className="overview-nums__value">{counts.queued}</div>
              <div className="small muted">排队</div>
            </div>
            <div>
              <div className={`overview-nums__value ${counts.failed > 0 ? 'overview-nums__value--error' : ''}`}>
                {counts.failed}
              </div>
              <div className="small muted">失败</div>
            </div>
            <div>
              <div className="overview-nums__value">{counts.done}</div>
              <div className="small muted">完成</div>
            </div>
          </div>
          {counts.running + counts.queued > 0 ? (
            <div className="chat-card__bar">
              <div
                className="chat-card__fill"
                style={{ width: `${Math.round(((counts.running + counts.queued) / Math.max(jobs.length, 1)) * 100)}%` }}
              />
            </div>
          ) : null}
        </>
      )}
    </CardShell>
  );
}
