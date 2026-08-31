/** 自建 subagent 定义变化通知(模块级 listener,不要 React Context)。
 *
 *  造人成功后 SpawnForm 触发 notify,DefinitionGrid 订阅后重拉。
 */

type DefsListener = () => void;

const listeners: Set<DefsListener> = new Set();

/** 订阅自建定义变化;返回退订函数。 */
export function onTeamDefsChanged(fn: DefsListener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** 触发一次自建定义变化通知。 */
export function notifyTeamDefsChanged(): void {
  listeners.forEach((fn) => fn());
}
