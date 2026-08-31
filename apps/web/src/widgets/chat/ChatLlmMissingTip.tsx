import { Link } from 'react-router-dom';
import { routes } from '@/utils/routes';

/** 无可用 LLM key 时的共用提示(Chat 页 / 悬浮窗)。 */
export function ChatLlmMissingTip() {
  return (
    <div className="degrade-tip" role="status">
      <span>
        还没有可用的 LLM 提供商:先到 <Link to={routes.settings}>设置 → LLM</Link>{' '}
        填 api key,再开始对话。
      </span>
    </div>
  );
}
