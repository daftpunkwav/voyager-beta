// @ts-nocheck — 迁移期:RepoPilot 风格代码,新 page / hook 仍按 strict 写(见各文件顶部注释)。
import { useCallback, useEffect, useRef, useState } from 'react';
import { getApi } from '@/api/client';
import type { LookTarget } from '@/components/agent/AgentAvatar';
import type { TrendingPeriod, TrendingRepo } from '@/api/types';
import { asSSETextDelta } from '@/utils/sse-helpers';

/** 离开全部 trending 项目后，延迟开始消失 */
export const TRENDING_SCOUT_LEAVE_DELAY_MS = 3000;
/** 与 CSS transition 时长一致 */
export const TRENDING_SCOUT_HIDE_ANIM_MS = 380;

export type TrendingScoutPhase = 'hidden' | 'visible' | 'leaving';

function repoKey(repo: TrendingRepo) {
  return `${repo.owner}/${repo.repo}`;
}

export function useTrendingScoutSpot(period: TrendingPeriod) {
  const [phase, setPhase] = useState<TrendingScoutPhase>('hidden');
  const [repo, setRepo] = useState<TrendingRepo | null>(null);
  const [content, setContent] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [lookTarget, setLookTarget] = useState<LookTarget | null>(null);

  const leaveTimerRef = useRef<number | null>(null);
  const hideAnimTimerRef = useRef<number | null>(null);
  const streamGenRef = useRef(0);
  const streamAbortRef = useRef<AbortController | null>(null);
  const activeRepoKeyRef = useRef<string | null>(null);
  /** 当前悬停中的 trending 卡片数（卡片间切换时短暂为 0，由 enter 取消 hide） */
  const cardHoverCountRef = useRef(0);

  const clearLeaveTimer = useCallback(() => {
    if (leaveTimerRef.current !== null) {
      window.clearTimeout(leaveTimerRef.current);
      leaveTimerRef.current = null;
    }
  }, []);

  const clearHideAnimTimer = useCallback(() => {
    if (hideAnimTimerRef.current !== null) {
      window.clearTimeout(hideAnimTimerRef.current);
      hideAnimTimerRef.current = null;
    }
  }, []);

  const abortStream = useCallback(() => {
    streamGenRef.current += 1;
    streamAbortRef.current?.abort();
    streamAbortRef.current = null;
    setIsStreaming(false);
  }, []);

  const finishHide = useCallback(() => {
    abortStream();
    cardHoverCountRef.current = 0;
    setPhase('hidden');
    setRepo(null);
    setContent('');
    setLookTarget(null);
    activeRepoKeyRef.current = null;
  }, [abortStream]);

  const startHide = useCallback(() => {
    clearLeaveTimer();
    clearHideAnimTimer();
    setPhase('leaving');
    hideAnimTimerRef.current = window.setTimeout(() => {
      finishHide();
    }, TRENDING_SCOUT_HIDE_ANIM_MS);
  }, [clearHideAnimTimer, clearLeaveTimer, finishHide]);

  const scheduleHide = useCallback(() => {
    clearLeaveTimer();
    leaveTimerRef.current = window.setTimeout(() => {
      if (cardHoverCountRef.current > 0) return;
      startHide();
    }, TRENDING_SCOUT_LEAVE_DELAY_MS);
  }, [clearLeaveTimer, startHide]);

  const startStream = useCallback(
    async (target: TrendingRepo) => {
      const gen = ++streamGenRef.current;
      const key = repoKey(target);
      activeRepoKeyRef.current = key;
      setContent('');
      setIsStreaming(true);

      try {
        streamAbortRef.current?.abort();
        const ac = new AbortController();
        streamAbortRef.current = ac;
        const stream = getApi().streamTrendingScoutIntro(
          {
            owner: target.owner,
            repo: target.repo,
            period,
          },
          ac.signal
        );

        for await (const event of stream) {
          if (streamGenRef.current !== gen || activeRepoKeyRef.current !== key) return;
          if (event.event === 'text_delta') {
            const delta = asSSETextDelta(event.data);
            setContent((prev) => prev + delta.content);
          } else if (event.event === 'error') {
            setContent('Scout 暂时无法生成介绍，请稍后再试。');
            break;
          }
        }
      } catch {
        if (streamGenRef.current === gen && activeRepoKeyRef.current === key) {
          setContent((prev) => prev || 'Scout 暂时无法生成介绍，请稍后再试。');
        }
      } finally {
        if (streamGenRef.current === gen && activeRepoKeyRef.current === key) {
          setIsStreaming(false);
        }
      }
    },
    [period],
  );

  const onTrendingCardEnter = useCallback(
    (target: TrendingRepo, look: LookTarget) => {
      cardHoverCountRef.current += 1;
      clearLeaveTimer();
      clearHideAnimTimer();
      setLookTarget(look);

      const key = repoKey(target);
      const isNewRepo = activeRepoKeyRef.current !== key;

      setRepo(target);
      setPhase('visible');

      if (isNewRepo) {
        void startStream(target);
      }
    },
    [clearHideAnimTimer, clearLeaveTimer, startStream],
  );

  const onTrendingCardLeave = useCallback(() => {
    cardHoverCountRef.current = Math.max(0, cardHoverCountRef.current - 1);
    if (cardHoverCountRef.current === 0) {
      scheduleHide();
    }
  }, [scheduleHide]);

  const cancelHide = useCallback(() => {
    clearLeaveTimer();
    clearHideAnimTimer();
    setPhase((current) => (current === 'leaving' ? 'visible' : current));
  }, [clearHideAnimTimer, clearLeaveTimer]);

  const showForRepo = useCallback(
    (target: TrendingRepo, look: LookTarget) => {
      onTrendingCardEnter(target, look);
    },
    [onTrendingCardEnter],
  );

  const leaveTrendingCard = useCallback(() => {
    onTrendingCardLeave();
  }, [onTrendingCardLeave]);

  const updateLook = useCallback((look: LookTarget) => {
    setLookTarget(look);
  }, []);

  useEffect(() => {
    cardHoverCountRef.current = 0;
    clearLeaveTimer();
    clearHideAnimTimer();
    finishHide();
  }, [period, clearHideAnimTimer, clearLeaveTimer, finishHide]);

  useEffect(
    () => () => {
      clearLeaveTimer();
      clearHideAnimTimer();
      abortStream();
    },
    [abortStream, clearHideAnimTimer, clearLeaveTimer],
  );

  return {
    phase,
    repo,
    content,
    isStreaming,
    lookTarget,
    showForRepo,
    leaveTrendingCard,
    updateLook,
    scheduleHide,
    cancelHide,
  };
}
