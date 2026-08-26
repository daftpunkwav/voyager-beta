import type { SVGProps } from 'react';

type IconProps = SVGProps<SVGSVGElement>;

function IconBase({ children, ...props }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      width={18}
      height={18}
      aria-hidden
      {...props}
    >
      {children}
    </svg>
  );
}

export const NavIcons = {
  chat: (props: IconProps) => (
    <IconBase {...props}>
      <path d="M21 15a3 3 0 0 1-3 3H8l-5 4V6a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3v9z" />
    </IconBase>
  ),
  team: (props: IconProps) => (
    <IconBase {...props}>
      {/* 两个人形(更清晰的"团队"语义,不再像 3 个点) */}
      <path d="M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6z" />
      <path d="M16 11a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z" />
      <path d="M2 20c0-3 2.5-5 6-5s6 2 6 5" />
      <path d="M14 20c0-2 1.8-3.5 4-3.5s4 1.5 4 3.5" />
    </IconBase>
  ),
  sources: (props: IconProps) => (
    <IconBase {...props}>
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
    </IconBase>
  ),
  graph: (props: IconProps) => (
    <IconBase {...props}>
      {/* 中心节点(实心) + 4 周围空心小圆 + 4 连线 — 网络拓扑感(非 3 圆点) */}
      <circle cx="12" cy="12" r="3.2" fill="currentColor" stroke="none" />
      <circle cx="4"  cy="4"  r="1.6" fill="none" />
      <circle cx="20" cy="4"  r="1.6" fill="none" />
      <circle cx="4"  cy="20" r="1.6" fill="none" />
      <circle cx="20" cy="20" r="1.6" fill="none" />
      <path d="M5.4 5.4L9.4 9.4M14.6 9.4L18.6 5.4M5.4 18.6L9.4 14.6M14.6 14.6L18.6 18.6" />
    </IconBase>
  ),
  activity: (props: IconProps) => (
    <IconBase {...props}>
      <path d="M3 12h4l3-7 4 14 3-7h4" />
    </IconBase>
  ),
  health: (props: IconProps) => (
    <IconBase {...props}>
      <path d="M3 12h4l2-5 4 10 2-5h6" />
    </IconBase>
  ),
  overview: (props: IconProps) => (
    <IconBase {...props}>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </IconBase>
  ),
  usage: (props: IconProps) => (
    <IconBase {...props}>
      <path d="M4 19V5" />
      <path d="M4 19h16" />
      <path d="M8 17V11" />
      <path d="M12 17V7" />
      <path d="M16 17v-4" />
    </IconBase>
  ),
  notes: (props: IconProps) => (
    <IconBase {...props}>
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </IconBase>
  ),
  settings: (props: IconProps) => (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3h.1a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8v.1a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
    </IconBase>
  ),
};
