/** 权限矩阵(只读,§9.9/§9.10):四维 × 当前值,从设置键读现状。
 * 点击单元格跳设置页 agent 分组修改(/settings?module=agent)。
 */

import { Link } from 'react-router-dom';
import type { MatrixSettings } from './teamStore';

const NETWORK_LABELS: Record<string, string> = {
  off: '关闭(不出网)',
  whitelist: '域名白名单',
  all: '全开',
};

export function PermissionMatrix({ matrix }: { matrix: MatrixSettings | null }) {
  if (!matrix) {
    return <div className="muted small">权限数据加载中…</div>;
  }
  const rows: { dim: string; value: string; detail: string }[] = [
    {
      dim: '网络',
      value: NETWORK_LABELS[matrix.networkMode] ?? matrix.networkMode,
      detail: matrix.networkMode === 'whitelist'
        ? matrix.networkDomains.join('、')
        : matrix.networkMode === 'off' ? '一切出网请求被拒' : '任意域名可访问',
    },
    {
      dim: '文件',
      value: `工作目录 ${matrix.workspaceDir}`,
      detail: '目录内可写,目录外只读不写(fs jail)',
    },
    {
      dim: '轮数',
      value: `${matrix.roundsMax} 轮 / ${matrix.roundsToolMax} 次工具`,
      detail: 'ReAct 轮数与工具调用是两个独立上限(超限体面中断)',
    },
    {
      dim: '应用内',
      value: '能力白名单 + secret 边界',
      detail: 'secret 项仅用户可写;能力入口强制校验(不靠提示词)',
    },
  ];
  return (
    <div className="matrix">
      <div className="node-editor__tabs">
        <span className="label">权限矩阵</span>
        <span className="small muted">只读;点击跳设置修改</span>
      </div>
      <table className="usage-table matrix__table">
        <tbody>
          {rows.map((r) => (
            <tr key={r.dim}>
              <td className="matrix__dim">{r.dim}</td>
              <td>
                <Link to="/settings?module=agent" className="matrix__cell">
                  {r.value}
                  <span className="small muted matrix__detail">{r.detail}</span>
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="small muted">
        并发:{matrix.maxConcurrent} 个 subagent 同时运行
      </div>
    </div>
  );
}
