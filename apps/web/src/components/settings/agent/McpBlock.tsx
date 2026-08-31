import { useEffect, useState } from 'react';
import { callCapability } from '@/bridge/client';
import { McpForm } from './McpForm';
import { McpList } from './McpList';
import type { McpServerState } from './types';

/** 外接 MCP:列表 + 添加表单 */
export function McpBlock() {
  const [servers, setServers] = useState<McpServerState[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  const reload = () =>
    callCapability<McpServerState[]>('agent', 'list_mcp_servers', {})
      .then((items) => setServers(Array.isArray(items) ? items : []))
      .catch(() => undefined); // 操作后刷新失败:静默保留现列表,toast 由调用方负责

  useEffect(() => {
    let alive = true;
    callCapability<McpServerState[]>('agent', 'list_mcp_servers', {})
      .then((items) => {
        if (alive) setServers(Array.isArray(items) ? items : []);
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">外接 MCP</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        添加后先列出它的工具，批准才会进对话工具面；领域笔记/图谱仍走内置能力，不要在这里填本仓库的 mcp_server。
      </p>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>读取失败请刷新。</p>
      ) : servers === null ? (
        <p className="muted" style={{ fontSize: 12 }}>外接 MCP 列表加载中…</p>
      ) : servers.length === 0 ? (
        <p className="muted" style={{ fontSize: 12 }}>
          还没有外接 MCP。用下面的表单添加一台 stdio 命令或 HTTP URL。
        </p>
      ) : (
        <McpList servers={servers} onChange={reload} />
      )}
      <McpForm onAdded={reload} />
    </div>
  );
}
