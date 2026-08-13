import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type MouseEvent } from 'react';
import { Link } from 'react-router-dom';
import { AgentAvatar, type LookTarget } from '@/components/agent/AgentAvatar';
import {
  AGENT_CAROUSEL_INTERVAL_MS,
  AGENT_CAROUSEL_TRANSITION_MS,
  AGENT_CAROUSEL_VISIBLE,
  AGENT_CATALOG,
  type AgentDefinition,
} from '@/constants/agentCatalog';
import { HERO_INNER_GLASS, HERO_OUTER_GLASS } from '@/constants/overviewGlass';

const GAP_PX = 16;
const MOBILE_BREAKPOINT_PX = 1200;
const MOBILE_VISIBLE_COUNT = 2;
/** 轮播卡片头像尺寸（54px × 1.2） */
const AGENT_AVATAR_SIZE = Math.round(54 * 1.2);

function useResponsiveVisibleCount(defaultCount: number) {
  const [count, setCount] = useState(defaultCount);

  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT_PX}px)`);
    const update = () => setCount(mq.matches ? MOBILE_VISIBLE_COUNT : defaultCount);
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, [defaultCount]);

  return count;
}

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(mq.matches);
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, []);

  return reduced;
}

function elementLookPoint(rect: DOMRect): LookTarget {
  return {
    x: rect.left + rect.width / 2,
    y: rect.top + rect.height / 2,
  };
}

function cardLookPoint(rect: DOMRect): LookTarget {
  return {
    x: rect.left + rect.width * 0.22,
    y: rect.top + rect.height * 0.42,
  };
}

function NavChevron({ direction }: { direction: 'prev' | 'next' }) {
  /* 张角 ×1.2（90° → 108°，半角 54°） */
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden>
      {direction === 'prev' ? (
        <path d="M14 3.74 L8 12 L14 20.26" strokeLinecap="round" strokeLinejoin="round" />
      ) : (
        <path d="M10 3.74 L16 12 L10 20.26" strokeLinecap="round" strokeLinejoin="round" />
      )}
    </svg>
  );
}

interface AgentCarouselProps {
  agents?: AgentDefinition[];
  visibleCount?: number;
  /** 外部注入的注视点（如总览页「和 Agent 对话」按钮悬停） */
  externalLookTarget?: LookTarget | null;
}

export function AgentCarousel({
  agents = AGENT_CATALOG,
  visibleCount = AGENT_CAROUSEL_VISIBLE,
  externalLookTarget = null,
}: AgentCarouselProps) {
  const resolvedVisible = useResponsiveVisibleCount(visibleCount);
  const prefersReducedMotion = usePrefersReducedMotion();
  const viewportRef = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const [noTransition, setNoTransition] = useState(false);
  const [stepPx, setStepPx] = useState(0);
  const [cardWidthPx, setCardWidthPx] = useState(0);
  const [lookTarget, setLookTarget] = useState<LookTarget | null>(null);
  const [focusedAgentId, setFocusedAgentId] = useState<string | null>(null);
  const indexRef = useRef(0);
  indexRef.current = index;

  const loopAgents = useMemo(
    () => (agents.length > resolvedVisible ? [...agents, ...agents] : agents),
    [agents, resolvedVisible],
  );

  const hasOverflow = agents.length > resolvedVisible;
  const autoScroll = hasOverflow && !prefersReducedMotion && !paused;

  useEffect(() => {
    setIndex(0);
    setNoTransition(false);
  }, [resolvedVisible, agents.length]);

  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;

    const measure = () => {
      const width = viewport.clientWidth;
      const slots = agents.length > resolvedVisible ? resolvedVisible : agents.length;
      const cardWidth = slots > 0 ? (width - GAP_PX * (slots - 1)) / slots : width;
      setCardWidthPx(cardWidth);
      setStepPx(cardWidth + GAP_PX);
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [resolvedVisible, agents.length]);

  useEffect(() => {
    if (!autoScroll) return;

    const timer = window.setInterval(() => {
      setIndex((prev) => prev + 1);
    }, AGENT_CAROUSEL_INTERVAL_MS);

    return () => window.clearInterval(timer);
  }, [autoScroll, agents.length]);

  useEffect(() => {
    if (!hasOverflow || index !== agents.length) return;

    const resetTimer = window.setTimeout(() => {
      setNoTransition(true);
      setIndex(0);
      requestAnimationFrame(() => {
        requestAnimationFrame(() => setNoTransition(false));
      });
    }, AGENT_CAROUSEL_TRANSITION_MS);

    return () => window.clearTimeout(resetTimer);
  }, [index, agents.length, hasOverflow]);

  const handleCarouselLeave = () => {
    setPaused(false);
    setLookTarget(null);
    setFocusedAgentId(null);
  };

  const handleCardEnter = (event: MouseEvent<HTMLAnchorElement>, agentId: string) => {
    setPaused(true);
    setFocusedAgentId(agentId);
    setLookTarget(cardLookPoint(event.currentTarget.getBoundingClientRect()));
  };

  const handleNavEnter = (event: MouseEvent<HTMLButtonElement>) => {
    setPaused(true);
    setFocusedAgentId(null);
    setLookTarget(elementLookPoint(event.currentTarget.getBoundingClientRect()));
  };

  const goNext = useCallback(() => {
    if (!hasOverflow) return;
    setPaused(true);
    setFocusedAgentId(null);
    setIndex((prev) => prev + 1);
  }, [hasOverflow]);

  const goPrev = useCallback(() => {
    if (!hasOverflow) return;
    setPaused(true);
    setFocusedAgentId(null);

    const prev = indexRef.current;
    if (prev > 0) {
      setIndex(prev - 1);
      return;
    }

    setNoTransition(true);
    setIndex(agents.length);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        setNoTransition(false);
        setIndex(agents.length - 1);
      });
    });
  }, [agents.length, hasOverflow]);

  const offsetPx = hasOverflow ? index * stepPx : 0;
  const trackTransition = noTransition
    ? 'none'
    : `transform ${AGENT_CAROUSEL_TRANSITION_MS}ms var(--ease)`;
  const effectiveLookTarget = externalLookTarget ?? lookTarget;
  const externalLookActive = externalLookTarget != null;

  return (
    <section
      className="agent-carousel"
      aria-label="Agent 入口"
      style={{ '--agent-visible': resolvedVisible, '--agent-gap': `${GAP_PX}px` } as CSSProperties}
      onMouseLeave={handleCarouselLeave}
    >
      <div className="agent-carousel-rail">
        {hasOverflow && (
          <button
            type="button"
            className={`agent-carousel-nav agent-carousel-nav--prev ${HERO_INNER_GLASS}`}
            aria-label="上一个 Agent"
            onClick={goPrev}
            onMouseEnter={handleNavEnter}
          >
            <NavChevron direction="prev" />
          </button>
        )}

        <div className="agent-carousel-shell">
          <div
            className="agent-carousel-viewport"
            ref={viewportRef}
            style={
              cardWidthPx
                ? ({ '--agent-card-width': `${cardWidthPx}px` } as CSSProperties)
                : undefined
            }
          >
            <div
              className="agent-carousel-track"
              style={{
                transform: `translateX(-${offsetPx}px)`,
                transition: trackTransition,
              }}
            >
              {loopAgents.map((agent, i) => (
                <Link
                  key={`${agent.id}-${i}`}
                  className="agent-carousel-card"
                  to={`/agent?agent=${agent.id}`}
                  onMouseEnter={(e) => handleCardEnter(e, agent.id)}
                >
                  <div className={`agent-card-glass ${HERO_OUTER_GLASS}`} aria-hidden />
                  <div className="agent-card-content">
                    <div className={`agent-card-meta ${HERO_INNER_GLASS}`}>
                      <AgentAvatar
                        agentId={agent.id}
                        lookTarget={effectiveLookTarget}
                        isFocused={!externalLookActive && focusedAgentId === agent.id}
                        size={AGENT_AVATAR_SIZE}
                        gazeRevision={index}
                      />
                      <div className="agent-name">{agent.name}</div>
                    </div>
                    <div className="agent-card-body">
                      <p className="agent-card-tagline">{agent.tagline}</p>
                      <p className="agent-card-intro">{agent.intro}</p>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </div>

        {hasOverflow && (
          <button
            type="button"
            className={`agent-carousel-nav agent-carousel-nav--next ${HERO_INNER_GLASS}`}
            aria-label="下一个 Agent"
            onClick={goNext}
            onMouseEnter={handleNavEnter}
          >
            <NavChevron direction="next" />
          </button>
        )}
      </div>
    </section>
  );
}
