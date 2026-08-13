/**
 * 从用户消息中识别 GitHub 仓库，并导入/绑定到当前会话。
 */
import type { IApiClient } from '@/api/client';
import type { Project, StarRepo } from '@/api/types';

export interface GithubRepoRef {
  owner: string;
  repo: string;
  url: string;
}

const URL_RE =
  /https?:\/\/github\.com\/([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+?)(?:\.git)?(?=[\s/#?]|$)/gi;
const OWNER_REPO_RE = /\b([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]{2,})\b/g;
/** 「学习 codex 源码」「codex的源码」等裸仓库名 */
const BARE_LEARN_RE =
  /(?:学习|研究|阅读|看看|了解|读一下|读读|分析|拆解)\s*(?:一下)?\s*([A-Za-z][\w.-]{1,40})\s*(?:的)?\s*(?:源码|代码|仓库|项目)/gi;
const BARE_SRC_RE = /(?:^|[^\w/])([A-Za-z][\w.-]{1,40})\s*(?:的)?\s*源码/gi;

const SKIP_OWNERS = new Set(['http', 'https', 'www']);
const SKIP_REPOS = new Set([
  'pull',
  'issues',
  'commit',
  'tree',
  'blob',
  'releases',
  'wiki',
  'actions',
  'settings',
]);

function normalizeRef(owner: string, repo: string): GithubRepoRef | null {
  const o = owner.trim();
  const r = repo.trim().replace(/\.git$/i, '');
  if (!o || !r) return null;
  if (SKIP_OWNERS.has(o.toLowerCase())) return null;
  if (SKIP_REPOS.has(r.toLowerCase())) return null;
  // 排除域名误匹配（如 github.com/openai）
  if (o.includes('.')) return null;
  return {
    owner: o,
    repo: r,
    url: `https://github.com/${o}/${r}`,
  };
}

function addRef(map: Map<string, GithubRepoRef>, ref: GithubRepoRef | null) {
  if (!ref) return;
  const key = `${ref.owner}/${ref.repo}`.toLowerCase();
  if (!map.has(key)) map.set(key, ref);
}

/** 从文本提取明确的 GitHub URL / owner/repo */
export function extractGithubRepoRefs(text: string): GithubRepoRef[] {
  const map = new Map<string, GithubRepoRef>();
  if (!text?.trim()) return [];

  for (const m of text.matchAll(URL_RE)) {
    const owner = m[1];
    const repo = m[2];
    if (owner && repo) addRef(map, normalizeRef(owner, repo));
  }

  // 去掉 URL 后再扫 owner/repo，避免 github.com/owner 误匹配
  const withoutUrls = text.replace(URL_RE, ' ');
  for (const m of withoutUrls.matchAll(OWNER_REPO_RE)) {
    const owner = m[1];
    const repo = m[2];
    if (!owner || !repo) continue;
    if (/^\d+$/.test(repo)) continue;
    addRef(map, normalizeRef(owner, repo));
  }
  return [...map.values()];
}

/** 从「学习 X 源码」类表述提取裸仓库名 */
export function extractBareRepoNames(text: string): string[] {
  const names = new Set<string>();
  if (!text?.trim()) return [];
  for (const re of [BARE_LEARN_RE, BARE_SRC_RE]) {
    re.lastIndex = 0;
    for (const m of text.matchAll(re)) {
      const n = (m[1] ?? '').trim();
      if (n.length >= 2 && n.length <= 40 && !n.includes('/')) names.add(n);
    }
  }
  return [...names];
}

function projectMatchesRef(p: Project, ref: GithubRepoRef): boolean {
  const name = (p.name || '').toLowerCase();
  const url = (p.url || '').toLowerCase();
  const key = `${ref.owner}/${ref.repo}`.toLowerCase();
  const urlNorm = ref.url.toLowerCase();
  return name === key || url === urlNorm || url.includes(`github.com/${key}`);
}

function pickExactSearchHit(items: StarRepo[], bareName: string): StarRepo | null {
  const q = bareName.toLowerCase();
  const exact = items.filter((s) => s.repo.toLowerCase() === q);
  if (exact.length === 0) return null;
  // 同名多仓：取 stars 最高
  return exact.reduce((a, b) => ((b.stars ?? 0) > (a.stars ?? 0) ? b : a));
}

async function resolveProjectId(
  api: IApiClient,
  ref: GithubRepoRef
): Promise<string | null> {
  // 先查已导入库
  try {
    const listed = await api.listProjects({
      search: ref.repo,
      page: 1,
      page_size: 50,
    });
    const hit = listed.data.items.find((p) => projectMatchesRef(p, ref));
    if (hit) return String(hit.id);
  } catch {
    /* 继续尝试导入 */
  }

  try {
    await api.importProjects([
      { owner: ref.owner, repo: ref.repo, url: ref.url },
    ]);
  } catch {
    // 可能已存在或网络失败；再查一次
  }

  try {
    const listed = await api.listProjects({
      search: ref.repo,
      page: 1,
      page_size: 50,
    });
    const hit = listed.data.items.find((p) => projectMatchesRef(p, ref));
    return hit ? String(hit.id) : null;
  } catch {
    return null;
  }
}

async function resolveBareName(
  api: IApiClient,
  bareName: string
): Promise<GithubRepoRef | null> {
  // 库内已有同名项目
  try {
    const listed = await api.listProjects({
      search: bareName,
      page: 1,
      page_size: 30,
    });
    const q = bareName.toLowerCase();
    const local = listed.data.items.filter((p) => {
      const repo = (p.name.split('/')[1] ?? p.name).toLowerCase();
      return repo === q || p.name.toLowerCase() === q;
    });
    if (local.length === 1) {
      const hit = local[0];
      if (!hit) return null;
      const [owner, repo] = hit.name.includes('/')
        ? hit.name.split('/')
        : ['', hit.name];
      if (owner && repo) {
        return normalizeRef(owner, repo);
      }
    }
    if (local.length > 1) {
      // 多命中时不做自动猜测
      return null;
    }
  } catch {
    /* fallthrough */
  }

  try {
    const searched = await api.searchGithubRepos(bareName);
    const hit = pickExactSearchHit(searched.data ?? [], bareName);
    if (!hit) return null;
    return normalizeRef(hit.owner, hit.repo);
  } catch {
    return null;
  }
}

/**
 * 识别消息中的仓库并绑定到会话。
 * @returns 更新后的 project_ids；无变化时返回 null
 */
export async function ensureSessionProjectsFromMessage(
  api: IApiClient,
  sessionId: string,
  message: string,
  currentIds: string[]
): Promise<string[] | null> {
  const refs = extractGithubRepoRefs(message);
  const bareNames = extractBareRepoNames(message);

  // 已有明确 owner/repo 时，跳过同名裸名搜索，减少误绑
  const coveredRepos = new Set(refs.map((r) => r.repo.toLowerCase()));
  for (const name of bareNames) {
    if (coveredRepos.has(name.toLowerCase())) continue;
    const resolved = await resolveBareName(api, name);
    if (resolved) {
      refs.push(resolved);
      coveredRepos.add(resolved.repo.toLowerCase());
    }
  }

  if (refs.length === 0) return null;

  const existing = new Set(currentIds.map(String));
  const toAdd: string[] = [];

  for (const ref of refs) {
    const id = await resolveProjectId(api, ref);
    if (id && !existing.has(id) && !toAdd.includes(id)) {
      toAdd.push(id);
    }
  }

  if (toAdd.length === 0) return null;

  const nextIds = [...currentIds.map(String), ...toAdd];
  await api.updateAgentSession(sessionId, { project_ids: nextIds });
  return nextIds;
}
