// @ts-nocheck — 迁移期:上游迁入的代码,字段重命名由 legacyApi 边界归一化,新 page / hook 仍按 strict 写(见各文件顶部注释)。
import { useEffect, useRef, useState, type CSSProperties, type MouseEvent as ReactMouseEvent } from 'react';
import { Link } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import {
  useActivities,
  useProjectStats,
  useTrending,
} from '@/hooks/useProjects';
import { useOverviewRecentNotes, useRecommendedProjects } from '@/hooks/useOverview';
import { useTrendingScoutSpot } from '@/hooks/useTrendingScoutSpot';
import { useQuery } from '@tanstack/react-query';
import { getApi } from '@/api/client';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { formatRelativeTime, formatDateTime } from '@/utils/date';
import { formatNumber, langCssClass, REPO_AVATAR_GRADIENTS, splitRepoName } from '@/utils/format';
import { activityItemHref } from '@/utils/overviewLinks';
import {
  HERO_INNER_GLASS,
  HERO_OUTER_GLASS,
  OVERVIEW_CHIP_GLASS,
  OVERVIEW_INNER_GLASS,
  OVERVIEW_OUTER_GLASS,
  OVERVIEW_SUMMARY_INNER_GLASS,
} from '@/constants/overviewGlass';
import { getMorseHopPx, HERO_MORSE_BITS, HERO_MORSE_INTERVAL_MS } from '@/utils/morse';
import { AgentCarousel } from '@/components/agent/AgentCarousel';
import { TrendingScoutSpot } from '@/components/agent/TrendingScoutSpot';
import type { LookTarget } from '@/components/agent/AgentAvatar';
import type { ProjectProgress, TrendingPeriod, TrendingRepo } from '@/api/types';

const PROGRESS_ROWS: Array<{ key: ProjectProgress; label: string; color: string }> = [
  { key: 'none', label: '待开始', color: 'fill-none' },
  { key: 'learning', label: '学习中', color: 'fill-learning' },
  { key: 'learned', label: '已学习', color: 'fill-learned' },
  { key: 'mastered', label: '已掌握', color: 'fill-mastered' },
];

const RECOMMEND_SLOT_COUNT = 5;
const ACTIVITY_SLOT_COUNT = 10;

export function OverviewPage() {
  const user = useAuthStore((s) => s.user);
  const { data: stats, isLoading: statsLoading } = useProjectStats();
  const { data: recommended = [] } = useRecommendedProjects(5);
  const { data: recentNotes = [] } = useOverviewRecentNotes(4);
  const { data: activities } = useActivities();
  const [period, setPeriod] = useState<TrendingPeriod>('weekly');
  const { data: trending = [] } = useTrending(period);

  const { data: profile } = useQuery({
    queryKey: ['userProfile'],
    queryFn: async () => (await getApi().getUserProfile()).data,
  });

  const trendingGridRef = useRef<HTMLDivElement>(null);
  const recentNotesPanelRef = useRef<HTMLDivElement>(null);
  const [scoutBubbleWidth, setScoutBubbleWidth] = useState<number | null>(null);
  const scout = useTrendingScoutSpot(period);
  const [chatBtnLookTarget, setChatBtnLookTarget] = useState<LookTarget | null>(null);
  const [morseTick, setMorseTick] = useState(0);

  useEffect(() => {
    const panel = recentNotesPanelRef.current;
    if (!panel) return;

    const syncWidth = () => {
      setScoutBubbleWidth(panel.getBoundingClientRect().width);
    };

    syncWidth();
    const ro = new ResizeObserver(syncWidth);
    ro.observe(panel);
    window.addEventListener('resize', syncWidth);

    return () => {
      ro.disconnect();
      window.removeEventListener('resize', syncWidth);
    };
  }, []);

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (mq.matches) return;

    const id = window.setInterval(() => {
      setMorseTick((t) => t + 1);
    }, HERO_MORSE_INTERVAL_MS);

    return () => window.clearInterval(id);
  }, []);

  const handleChatBtnLook = (event: ReactMouseEvent<HTMLAnchorElement>) => {
    setChatBtnLookTarget({ x: event.clientX, y: event.clientY });
  };

  const handleChatBtnLookEnd = () => {
    setChatBtnLookTarget(null);
  };

  useEffect(() => {
    const grid = trendingGridRef.current;
    if (!grid || trending.length === 0) return;

    const cards = grid.querySelectorAll<HTMLElement>('.trending-card');
    cards.forEach((card) => card.classList.remove('is-visible'));

    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (mq.matches) {
      cards.forEach((card) => card.classList.add('is-visible'));
      return;
    }

    if (typeof IntersectionObserver === 'undefined') {
      cards.forEach((card) => card.classList.add('is-visible'));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const el = entry.target as HTMLElement;
          const idx = Number(el.dataset.index) || 0;
          window.setTimeout(
            () => el.classList.add('is-visible'),
            Math.min(idx * 60, 800),
          );
          observer.unobserve(el);
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -40px 0px' },
    );

    cards.forEach((card) => observer.observe(card));
    return () => observer.disconnect();
  }, [period, trending]);

  if (statsLoading) return <LoadingSpinner />;

  const total = stats?.total ?? 0;
  const byProgress = stats?.by_progress ?? {
    none: 0,
    learning: 0,
    learned: 0,
    mastered: 0,
  };
  const maxProgress = Math.max(...PROGRESS_ROWS.map((p) => byProgress[p.key] ?? 0), 1);

  const username = user?.username ?? '同学';
  const heroLede = user
    ? `本地学习者 · 创建于 ${formatDateTime(user.created_at)} · GitHub 已绑定（@${user.github_login ?? 'unknown'}）`
    : `你的项目库有 ${total} 个项目等待探索`;

  const MIN_TREND_W = 38;
  const trendStep = trending.length > 1 ? (100 - MIN_TREND_W) / (trending.length - 1) : 0;

  const handleTrendingCardEnter = (repo: TrendingRepo, event: ReactMouseEvent<HTMLAnchorElement>) => {
    scout.showForRepo(repo, { x: event.clientX, y: event.clientY });
  };

  const handleTrendingCardLeave = () => {
    scout.leaveTrendingCard();
  };

  const handleTrendingCardMove = (event: ReactMouseEvent<HTMLAnchorElement>) => {
    scout.updateLook({ x: event.clientX, y: event.clientY });
  };

  const heroArtChars = ['R', 'e', 'p', 'o', 'P', 'i', 'l', 'o', 't'];

  const morseActiveIndex = morseTick % heroArtChars.length;
  const morseBit = HERO_MORSE_BITS[morseTick % HERO_MORSE_BITS.length] ?? 0;
  const morseRound = Math.floor(morseTick / HERO_MORSE_BITS.length);
  const morseInvert = morseRound % 2 === 1;

  const recommendSlots = Array.from({ length: RECOMMEND_SLOT_COUNT }, (_, i) => recommended[i] ?? null);
  const activityItems = (activities ?? []).slice(0, ACTIVITY_SLOT_COUNT);

  return (
    <>
      <div className="overview-hero-wrap" data-testid="overview-hero">
        <div className="overview-hero-art" aria-hidden>
          <span className="overview-hero-artword">
            {heroArtChars.map((char, index) => {
              const isMorseActive = index === morseActiveIndex;
              const hopPx = isMorseActive ? getMorseHopPx(index, morseBit, morseInvert) : 0;

              return (
                <span key={`${char}-${index}`} className="overview-hero-art-char">
                  <span
                    key={isMorseActive ? `morse-${morseTick}` : 'rest'}
                    className={`overview-hero-art-char-glyph${isMorseActive ? ' morse-hopping' : ''}`}
                    style={
                      isMorseActive
                        ? ({ '--morse-hop': `${hopPx}px` } as CSSProperties)
                        : undefined
                    }
                  >
                    {char}
                  </span>
                </span>
              );
            })}
          </span>
        </div>
        <div className={`overview-hero-glass ${HERO_OUTER_GLASS}`} aria-hidden />
        <section className="overview-hero-content">
          <h1>
            你好，<span>{username}</span> 👋
          </h1>
          <p className="lede">{heroLede}</p>
          <div className="quick-actions">
            <Link
              to="/agent"
              className={`btn ${HERO_INNER_GLASS} liquid-glass--pulse liquid-glass-btn quick-action-brand`}
              onMouseEnter={handleChatBtnLook}
              onMouseMove={handleChatBtnLook}
              onMouseLeave={handleChatBtnLookEnd}
            >
              和 Agent 对话
            </Link>
            <Link
              to="/projects"
              className={`btn ${HERO_INNER_GLASS} liquid-glass-btn`}
            >
              浏览项目库
            </Link>
            <Link
              to="/graph"
              className={`btn ${HERO_INNER_GLASS} liquid-glass-btn`}
            >
              查看图谱
            </Link>
            <Link
              to="/settings"
              className={`btn ${HERO_INNER_GLASS} liquid-glass-btn`}
            >
              设置
            </Link>
          </div>
        </section>
      </div>

      <AgentCarousel externalLookTarget={chatBtnLookTarget} />

      <section className="row-2col row-2col--phi">
        <div className={`panel panel-progress ${OVERVIEW_OUTER_GLASS}`} data-testid="overview-progress">
          <h3>学习进度分布</h3>
          <div className="progress-panel-body">
            <section
              className={`agent-summary progress-panel-summary ${OVERVIEW_SUMMARY_INNER_GLASS}`}
              aria-label="Mentor 学习周报"
            >
              <div className="summary-head">
                <div className={`summary-avatar ${OVERVIEW_CHIP_GLASS}`}>M</div>
                <div className="summary-meta">
                  <div className="summary-agent">Mentor · 本周学习总结</div>
                  <div className="summary-time">由 AI 自动生成</div>
                </div>
                <span className={`summary-badge ${OVERVIEW_CHIP_GLASS}`}>AI</span>
              </div>
              <div className="summary-body">
                <p>
                  {profile?.history_summary ??
                    `${username}，本周继续保持学习节奏，Agent 将为你生成个性化周报。`}
                </p>
              </div>
            </section>
            <div className="progress-overview">
              <p className="progress-section-title">分类总览</p>
              <div className="progress-bars">
                {PROGRESS_ROWS.map((p) => {
                  const v = byProgress[p.key] ?? 0;
                  const pct = Math.round((v / maxProgress) * 100);
                  return (
                    <div key={p.key} className="progress-row">
                      <span className="pl">{p.label}</span>
                      <div className="track">
                        <div className={`fill ${p.color}`} style={{ width: `${pct}%` }} />
                      </div>
                      <span className="pv">{v}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        <div className={`panel panel-activity ${OVERVIEW_OUTER_GLASS}`} data-testid="overview-activities">
          <div className="section-head" style={{ marginTop: 0 }}>
            <h3>最近活动</h3>
            <Link
              to="/agent"
              className={`more ${HERO_INNER_GLASS}`}
            >
              查看全部 →
            </Link>
          </div>
          <div className="activity-list">
            {activityItems.length === 0 ? (
              <div className="panel-empty">暂无活动</div>
            ) : (
              activityItems.map((a) => (
                <Link
                  key={a.id}
                  className={`activity-item ${OVERVIEW_INNER_GLASS}`}
                  to={activityItemHref(a)}
                  data-testid="overview-activity-item"
                >
                  <div className="activity-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={14} height={14}>
                      <path d="M21 15a3 3 0 0 1-3 3H8l-5 4V6a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3v9z" />
                    </svg>
                  </div>
                  <div className="activity-body">
                    <div className="activity-title">{a.title}</div>
                    <div className="activity-desc">{a.description}</div>
                  </div>
                  <span className="activity-time">{formatRelativeTime(a.created_at)}</span>
                </Link>
              ))
            )}
          </div>
        </div>
      </section>

      <section className="row-2col row-2col--phi">
        <div className={`panel panel-recommend ${OVERVIEW_OUTER_GLASS}`} data-testid="overview-recommendations">
          <h3 className="panel-title-with-sub">
            为你推荐
            <span className="panel-title-sub">Agent 根据学习记录和喜好推荐</span>
          </h3>
          <div className="project-list">
            {recommendSlots.map((item, i) => {
              if (!item) {
                return (
                  <div
                    key={`rec-empty-${i}`}
                    className={`project-item project-item--placeholder ${OVERVIEW_INNER_GLASS}`}
                    aria-hidden
                  >
                    <div
                      className="project-avatar"
                      style={{ background: REPO_AVATAR_GRADIENTS[i % REPO_AVATAR_GRADIENTS.length] }}
                    >
                      ·
                    </div>
                    <div className="project-info">
                      <div className="project-name">推荐加载中…</div>
                      <p className="project-desc">Agent 正在根据学习记录生成推荐</p>
                    </div>
                  </div>
                );
              }
              const { owner, repo } = splitRepoName(item.name);
              return (
                <Link
                  key={item.id}
                  className={`project-item ${OVERVIEW_INNER_GLASS}`}
                  to={`/projects/${item.project_id}`}
                  aria-describedby={`rec-reason-${item.id}`}
                  data-testid="overview-recommend-item"
                >
                    <div
                      className="project-avatar"
                      style={{ background: REPO_AVATAR_GRADIENTS[i % REPO_AVATAR_GRADIENTS.length] }}
                    >
                      {(repo[0] ?? '?').toUpperCase()}
                    </div>
                    <div className="project-info">
                      <div className="project-name">
                        <span className="owner">{owner}</span>
                        <span className="slash">/</span>
                        <span>{repo}</span>
                      </div>
                      <div className="project-desc-swap">
                        <p className="project-desc">{item.description ?? ''}</p>
                        <p className="project-reason" id={`rec-reason-${item.id}`}>
                          {item.reason}
                        </p>
                      </div>
                    </div>
                    <span className="project-stars">⭐ {formatNumber(item.stars)}</span>
                  </Link>
                );
              })}
          </div>
        </div>

        <div
          className={`panel panel-notes ${OVERVIEW_OUTER_GLASS}`}
          ref={recentNotesPanelRef}
          data-testid="overview-notes"
        >
          <div className="section-head" style={{ marginTop: 0 }}>
            <h3>最近笔记</h3>
            <Link
              to="/notes"
              className={`more ${HERO_INNER_GLASS}`}
            >
              查看全部 →
            </Link>
          </div>
          <div className="notes-list">
            {recentNotes.length === 0 ? (
              <div className="panel-empty">暂无笔记</div>
            ) : (
              recentNotes.map((n) => (
                <Link
                  key={n.id}
                  className={`note-item ${OVERVIEW_INNER_GLASS}`}
                  to={`/projects/${n.project_id}`}
                  data-testid="overview-note-item"
                >
                  <div className="note-title">{n.title}</div>
                  <div className="note-meta">
                    <span className="tag-link">{n.project_name}</span>
                    <span>·</span>
                    <span>{formatRelativeTime(n.updated_at)}</span>
                  </div>
                </Link>
              ))
            )}
          </div>
        </div>
      </section>

      <section className="trending-section" data-testid="overview-trending">
        <div className="trending-head">
          <div className="trending-head-left">
            <h2>GitHub 近期热门</h2>
            <span className="trending-subtitle">基于 trending 数据，帮助你发现值得关注的项目</span>
          </div>
          <div className="period-toggle glass-card glass-card--panel-clear" role="tablist">
            {(['daily', 'weekly', 'monthly'] as TrendingPeriod[]).map((p) => (
              <button
                key={p}
                type="button"
                className={`period-btn liquid-glass--pill${
                  period === p ? ` ${HERO_INNER_GLASS} active` : ''
                }`}
                onClick={() => setPeriod(p)}
              >
                {p === 'daily' ? '今日' : p === 'weekly' ? '本周' : '本月'}
              </button>
            ))}
          </div>
        </div>
        <div className="trending-grid" ref={trendingGridRef}>
            {trending.length === 0 ? (
              <div className="trending-empty">该周期暂无数据</div>
            ) : (
              trending.slice(0, 50).map((r, index) => {
                const widthPct = Math.max(100 - index * trendStep, MIN_TREND_W);
                const { owner, repo } = splitRepoName(`${r.owner}/${r.repo}`);
                return (
                  <a
                    key={`${period}-${r.owner}/${r.repo}`}
                    data-index={index}
                    className={`trending-card ${OVERVIEW_INNER_GLASS}`}
                    data-testid="overview-trending-card"
                    style={{ ['--card-w' as string]: `${widthPct.toFixed(2)}%` }}
                    href={r.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    onMouseEnter={(event) => handleTrendingCardEnter(r, event)}
                    onMouseLeave={handleTrendingCardLeave}
                    onMouseMove={handleTrendingCardMove}
                  >
                  <div className={`trending-rank ${OVERVIEW_CHIP_GLASS}`}>{r.rank ?? index + 1}</div>
                  <div className="trending-body">
                    <div className="trending-name">
                      <span className="owner">{owner}</span>
                      <span className="slash">/</span>
                      <span>{repo}</span>
                    </div>
                    <div className="trending-desc">{r.description ?? ''}</div>
                    <div className="trending-meta">
                      <span className={`lang-dot ${langCssClass(r.language)}`}>
                        {r.language ?? '-'}
                      </span>
                      <span className="stars">★ {formatNumber(r.stars)}</span>
                    </div>
                  </div>
                </a>
              );
            })
          )}
        </div>
      </section>

      <TrendingScoutSpot
        phase={scout.phase}
        repo={scout.repo}
        content={scout.content}
        isStreaming={scout.isStreaming}
        lookTarget={scout.lookTarget}
        bubbleWidthPx={scoutBubbleWidth}
      />
    </>
  );
}
