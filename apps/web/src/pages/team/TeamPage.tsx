/** 团队 — Agent 与 subagent 管理(基于 agent.list_subagents / list_personas / list_tools)。
 *
 * 本页为纯组装壳,按业务顺序排五块;各块自己加载、自己持 state、自己 toast。
 */

import { PersonaGrid } from './PersonaGrid';
import { DefinitionGrid } from './DefinitionGrid';
import { SpawnForm } from './SpawnForm';
import { ToolCatalog } from './ToolCatalog';
import { InstanceList } from './InstanceList';

export function TeamPage() {
  return (
    <div className="team-page page-scaffold">
      <div className="page-scaffold__body">
        <PersonaGrid />
        <DefinitionGrid />
        <SpawnForm />
        <ToolCatalog />
        <InstanceList />
      </div>
    </div>
  );
}

export default TeamPage;
