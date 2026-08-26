// @ts-nocheck — 迁移期:RepoPilot 风格代码,新 page / hook 仍按 strict 写(见各文件顶部注释)。
import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import {
  applyOverviewScenarioIfMock,
  getApiClient,
} from '@/api/client';
import {
  readOverviewMockRound,
  syncOverviewMockRoundFromUrl,
} from '@/api/mock/data/overviewScenarios';
import { invalidateOverviewQueries } from '@/utils/invalidateOverview';

/**
 * 同步 URL ?mock_round= → localStorage，并重新加载 Mock 总览 snapshot。
 * 解决：客户端改 URL 不刷新、刷新后 Query 缓存与 Mock 内存态不一致。
 *
 * 此 hook 只在 VITE_USE_MOCK=true 时生效；切到真实后端后调用即变成 no-op。
 */
export function useOverviewMockRoundSync() {
  const [searchParams] = useSearchParams();
  const qc = useQueryClient();
  const mockRoundParam = searchParams.get('mock_round');

  useEffect(() => {
    void (async () => {
      syncOverviewMockRoundFromUrl(window.location.href);
      const round = readOverviewMockRound();
      const client = await getApiClient();
      if (!applyOverviewScenarioIfMock(client, round)) return;
      await invalidateOverviewQueries(qc);
    })();
  }, [mockRoundParam, qc]);
}
