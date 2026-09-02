/** 团队页各块共用的类型定义。 */

/** 运行中 subagent 实例(来自 list_subagents.running)。 */
export interface RunningSubagent {
  id: string;
  name: string;
  status: string;
  goal: string;
  started_ts: number;
  last_step?: string;
}

/** 可恢复 checkpoint 条目(来自 list_resumable_checkpoints.items,phase-69/70;
 *  仅任务型 REACT、带恢复快照;status 为盘上状态,boot 后为 paused)。 */
export interface ResumableCheckpoint {
  run_id: string;
  status: string;
  goal: string;
  instance_name: string;
  started_ts: number;
  last_step?: string;
  mode: string;
}

/** list_subagents.definitions 条目;allowed_tools 为 null 表示不裁剪(全部工具);
 *  轮数为 null 表示跟随全局,网络档位空串表示继承全局(phase-10)。 */
export interface SubagentDef {
  name: string;
  mode: string;
  description: string;
  persona: string;
  allowed_tools: string[] | null;
  max_rounds?: number | null;
  max_tool_calls?: number | null;
  network_mode?: string;
}

/** 人格预设条目(来自 list_personas)。 */
export interface PersonaItem {
  key: string;
  display_name: string;
  style: string;
  default_mode: string;
  tool_allow: string[] | null;
  system_prompt: string;
}

/** 工具面名册条目(来自 list_tools)。 */
export interface ToolItem {
  name: string;
  description: string;
}
