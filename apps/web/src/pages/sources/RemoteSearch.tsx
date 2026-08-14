/** 库外搜索与 stars 面板:勾选批量导入;未配 token 限流时引导设置页。 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { callCapability, ServiceError } from '@/bridge/client';
import { useSourcesStore } from './sourcesStore';

interface RemoteRepo {
  owner: string;
  name: string;
  url: string;
  description: string;
  stars: number;
  language: string;
}

export function RemoteSearch({ onDone }: { onDone: () => void }) {
  const importUrls = useSourcesStore((s) => s.importUrls);
  const [tab, setTab] = useState<'search' | 'stars'>('search');
  const [query, setQuery] = useState('');
  const [username, setUsername] = useState('');
  const [results, setResults] = useState<RemoteRepo[] | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const search = async () => {
    setBusy(true);
    setError(null);
    setResults(null);
    try {
      if (tab === 'search') {
        setResults(
          await callCapability<RemoteRepo[]>('sources', 'search_remote_repos', {
            query,
            limit: 10,
          }),
        );
      } else {
        setResults(
          await callCapability<RemoteRepo[]>('sources', 'list_starred_repos', {
            username,
            limit: 50,
          }),
        );
      }
    } catch (err) {
      setError((err as ServiceError).message);
    } finally {
      setBusy(false);
    }
  };

  const importPicked = async () => {
    if (picked.size === 0) return;
    setBusy(true);
    await importUrls([...picked], '');
    setBusy(false);
    onDone();
  };

  const toggle = (url: string) => {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(url)) next.delete(url);
      else next.add(url);
      return next;
    });
  };

  return (
    <div className="import-dialog">
      <div className="repo-search__tabs">
        <button
          type="button"
          className={`btn ${tab === 'search' ? 'btn-primary' : ''}`}
          onClick={() => {
            setTab('search');
            setResults(null);
          }}
        >
          库外搜索
        </button>
        <button
          type="button"
          className={`btn ${tab === 'stars' ? 'btn-primary' : ''}`}
          onClick={() => {
            setTab('stars');
            setResults(null);
          }}
        >
          我的 Stars
        </button>
      </div>
      {tab === 'search' ? (
        <input
          className="setting-input"
          value={query}
          placeholder="搜索 GitHub 仓库,如 langgraph"
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && query.trim()) void search();
          }}
        />
      ) : (
        <input
          className="setting-input"
          value={username}
          placeholder="GitHub 用户名"
          onChange={(e) => setUsername(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && username.trim()) void search();
          }}
        />
      )}
      <p className="small muted">
        GitHub 未配 token 时有 60 次/小时限流;可到
        <Link to="/settings" className="repo-search__link">
          设置 → 资源库
        </Link>
        配置 sources.github.token(仅用户本人)。
      </p>
      {error ? <div className="setting-field__error small">{error}</div> : null}
      {results ? (
        <div className="repo-search__results">
          {results.length === 0 ? <span className="small muted">无结果</span> : null}
          {results.map((r) => (
            <label key={r.url} className="repo-search__row">
              <input
                type="checkbox"
                checked={picked.has(r.url)}
                onChange={() => toggle(r.url)}
              />
              <span className="repo-search__name">
                {r.owner}/{r.name}
              </span>
              <span className="small muted">★ {r.stars}</span>
              <span className="small muted">{r.language}</span>
            </label>
          ))}
        </div>
      ) : null}
      <div className="ask-actions">
        <button
          type="button"
          className="btn"
          disabled={busy || (tab === 'search' ? !query.trim() : !username.trim())}
          onClick={() => void search()}
        >
          {busy ? '查询中…' : tab === 'search' ? '搜索' : '列出 stars'}
        </button>
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy || picked.size === 0}
          onClick={() => void importPicked()}
        >
          导入选中({picked.size})
        </button>
        <button type="button" className="btn" onClick={onDone}>
          关闭
        </button>
      </div>
    </div>
  );
}
