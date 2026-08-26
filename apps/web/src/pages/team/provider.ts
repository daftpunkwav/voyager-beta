/** 团队页面 provider(§5.1) — 当前未对接真实 personas,先返回空摘要。 */

import type { PageProbe } from '@/bridge/pageContext';

export const teamProvider: PageProbe = {
  page: 'team',
  report() {
    return null;
  },
};
