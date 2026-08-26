export interface ValidationResult {
  valid: boolean;
  message?: string;
}

const GITHUB_URL_RE = /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/?$/;

export function validateGithubUrl(url: string): ValidationResult {
  const trimmed = url.trim();
  if (!GITHUB_URL_RE.test(trimmed)) {
    return { valid: false, message: '请输入有效的 GitHub 仓库 URL' };
  }
  return { valid: true };
}

export function parseGithubUrl(url: string): { owner: string; repo: string; name: string } | null {
  const match = trimmedGithubUrl(url).match(/^https:\/\/github\.com\/([^/]+)\/([^/]+)/);
  if (!match?.[1] || !match[2]) return null;
  const owner = match[1];
  const repo = match[2].replace(/\.git$/, '');
  return { owner, repo, name: `${owner}/${repo}` };
}

function trimmedGithubUrl(url: string): string {
  return url.trim().replace(/\/$/, '');
}

export function validateGithubUrls(text: string): {
  valid: Array<{ owner: string; repo: string; url: string; name: string }>;
  invalid: string[];
} {
  const lines = text.split('\n').map((l) => l.trim()).filter(Boolean);
  const valid: Array<{ owner: string; repo: string; url: string; name: string }> = [];
  const invalid: string[] = [];

  for (const line of lines) {
    const parsed = parseGithubUrl(line);
    if (parsed) {
      valid.push({
        ...parsed,
        url: `https://github.com/${parsed.owner}/${parsed.repo}`,
      });
    } else {
      invalid.push(line);
    }
  }
  return { valid, invalid };
}
