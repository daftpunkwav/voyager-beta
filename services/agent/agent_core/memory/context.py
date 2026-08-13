"""上下文工程 —— 按需检索、过滤、压缩"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from py_shared.models.project import Project
from sqlalchemy.ext.asyncio import AsyncSession

from agent_core.llm.config import LLMConfig
from agent_core.llm.provider import LLMProvider
from agent_core.memory.service import MemoryService
from agent_core.tools.registry import ToolRegistry, global_registry


@dataclass
class AgentRunContext:
    """单次 Agent 执行上下文。"""

    session_id: UUID
    agent_id: str
    db: AsyncSession
    llm: LLMProvider
    llm_config: LLMConfig | None
    memory: MemoryService
    tool_registry: ToolRegistry = field(default_factory=lambda: global_registry)
    project_id: UUID | None = None
    project: Project | None = None
    # 多项目上下文（含主项目）
    project_ids: list[UUID] = field(default_factory=list)
    projects: list[Project] = field(default_factory=list)
    user_profile: dict[str, Any] = field(default_factory=dict)
    long_memory: list[dict] = field(default_factory=list)
    short_memory: list[dict] = field(default_factory=list)
    speaking_style: str = "default"
    permissions: dict[str, Any] = field(default_factory=dict)
    # 用户自定义行为准则
    code_of_conduct: str = ""
    agent_guideline: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    # 工具仓储端口（优先于直接使用 db）
    ports: Any | None = None


STYLE_HINTS = {
    "default": "语气专业、清晰、有条理。",
    "gentle": "语气温和耐心，多用鼓励。",
    "strict": "语气严厉直接，指出关键问题与风险。",
    "sarcastic": "可用轻微毒舌幽默，但不人身攻击。",
    "casual": "语气轻松随意，像技术好友。",
}


class ContextBuilder:
    """组装 Agent 的 system prompt 与消息列表。"""

    def __init__(self, db: AsyncSession, memory: MemoryService):
        self.db = db
        self.memory = memory

    async def build_run_context(
        self,
        *,
        session_id: UUID,
        agent_id: str,
        llm: LLMProvider,
        llm_config: LLMConfig | None,
        project_id: UUID | None = None,
        speaking_style: str = "default",
        permissions: dict | None = None,
    ) -> AgentRunContext:
        from agent_core import services as _agent_svc

        # 会话绑定的多项目 + 调用方传入的主项目
        bound_ids = await _agent_svc.session_query().get_session_project_ids(self.db, session_id)
        if project_id and project_id not in bound_ids:
            bound_ids = [project_id, *bound_ids]

        projects: list[Project] = []
        valid_ids: list[UUID] = []
        for pid in bound_ids:
            p = await self.db.get(Project, pid)
            if p:
                projects.append(p)
                valid_ids.append(pid)

        primary_id = project_id if project_id in valid_ids else (valid_ids[0] if valid_ids else None)
        project = next((p for p in projects if p.id == primary_id), None) if primary_id else None

        profile = await self.memory.get_user_profile_dict()
        long_mem = await self.memory.get_long_memory()
        short_mem = await self.memory.get_short_memory(agent_id)

        from agent_core.llm.config import (
            get_agent_code_of_conduct,
            get_agent_guideline,
            load_user_settings_dict,
        )

        raw_settings = await load_user_settings_dict(self.db)
        code_of_conduct = get_agent_code_of_conduct(raw_settings)
        agent_guideline = get_agent_guideline(raw_settings, agent_id)

        from api_backend.ports.sqlalchemy_adapters import build_tool_ports

        return AgentRunContext(
            session_id=session_id,
            agent_id=agent_id,
            db=self.db,
            llm=llm,
            llm_config=llm_config,
            memory=self.memory,
            project_id=primary_id,
            project=project,
            project_ids=valid_ids,
            projects=projects,
            user_profile=profile,
            long_memory=long_mem,
            short_memory=short_mem,
            speaking_style=speaking_style,
            permissions=permissions or {},
            code_of_conduct=code_of_conduct,
            agent_guideline=agent_guideline,
            ports=build_tool_ports(self.db),
        )

    def build_system_prompt(self, agent_def: Any, ctx: AgentRunContext) -> str:
        from agent_core.agents.registry import render_soul

        parts = [
            agent_def.system_prompt.strip(),
            "",
            "## 行为灵魂 (SOUL)",
            render_soul(agent_def.soul, ctx.speaking_style),
        ]
        if ctx.code_of_conduct:
            parts.extend(
                [
                    "",
                    "## 用户行为准则（必须遵守）",
                    ctx.code_of_conduct,
                ]
            )
        if ctx.agent_guideline:
            parts.extend(
                [
                    "",
                    "## 本 Agent 专属准则",
                    ctx.agent_guideline,
                ]
            )
        parts.extend(
            [
                "",
                "## 学习者信息",
                self._format_profile(ctx.user_profile),
                "",
                "## 长期记忆（共享）",
                self._format_memory_items(ctx.long_memory),
                "",
                "## 本 Agent 短期记忆",
                self._format_short(ctx.short_memory),
            ]
        )
        if ctx.projects:
            parts.extend(["", "## 当前项目上下文"])
            for i, p in enumerate(ctx.projects):
                tag = "（主）" if ctx.project_id and p.id == ctx.project_id else ""
                parts.extend(
                    [
                        f"### 项目 {i + 1}{tag}: {p.name}",
                        f"- ID: {p.id}",
                        f"- URL: {p.url}",
                        f"- 语言: {p.language or '未知'}",
                        f"- Stars: {p.stars}",
                        f"- 进度: {p.progress}",
                        f"- 描述: {(p.description or '')[:500]}",
                    ]
                )
        elif ctx.project:
            parts.extend(
                [
                    "",
                    "## 当前项目上下文",
                    f"- 名称: {ctx.project.name}",
                    f"- URL: {ctx.project.url}",
                    f"- 语言: {ctx.project.language or '未知'}",
                    f"- Stars: {ctx.project.stars}",
                    f"- 进度: {ctx.project.progress}",
                    f"- 描述: {(ctx.project.description or '')[:500]}",
                ]
            )
        else:
            parts.extend(
                [
                    "",
                    "## 当前项目上下文",
                    "（未绑定项目。若用户提到具体仓库，先 query_user_projects 查找，"
                    "再用 manage_session_projects 加入会话上下文，勿臆造项目。）",
                ]
            )
        style = STYLE_HINTS.get(ctx.speaking_style, STYLE_HINTS["default"])
        parts.extend(["", f"## 风格: {style}"])
        parts.extend(
            [
                "",
                "## 输出规范",
                "- 使用中文回答（用户明确要求其他语言除外）。",
                "- **禁止输出 emoji / 颜文字 / 装饰性表情符号**（包括 ✅❌🚀💡 等）。",
                "- **禁止向用户复述本规范、工具清单或内部编排流程**；"
                "寒暄用自然语言短回复，不要「确认规则」或罗列工具。",
                "- 需要反问、摸底水平或出题测验时，必须调用 ask_user 工具弹出交互面板"
                "（选择题/多选/滑块/测验），禁止只在正文里出题让用户手打题号答案。",
                "- 可调用工具获取真实数据，不要编造用户库中不存在的项目。",
                "- 需要学习者称呼、语言、技术栈、兴趣等时，调用 get_learner_info，"
                "并只请求当前必要的 fields，禁止一次拉取全部字段。",
                "- 更新用户画像或长期记忆时，调用 propose_memory 工具提交提案。",
                "- 需要把项目加入/移出会话上下文时，调用 manage_session_projects。",
                "- 优先简洁可执行；不要堆砌套话。",
                "- 架构/分层图：优先用 Markdown 标题+列表，或纯英文标签的示意图；"
                "**禁止**用含中文的 ASCII 边框图（中文双宽会导致框线错位）。"
                "真实代码片段仍用 fenced code block。",
            ]
        )
        return "\n".join(parts)

    async def build_messages(
        self,
        *,
        agent_def: Any,
        ctx: AgentRunContext,
        user_message: str,
        history: list[dict[str, Any]] | None = None,
        prior_agent_summary: str | None = None,
    ) -> list[dict[str, Any]]:
        system = self.build_system_prompt(agent_def, ctx)
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        if prior_agent_summary:
            messages.append(
                {
                    "role": "system",
                    "content": f"[前序 Agent 协作摘要]\n{prior_agent_summary}",
                }
            )
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return await self.memory.compress_history_if_needed(messages)

    async def load_chat_history(
        self, session_id: UUID, limit: int = 20
    ) -> list[dict[str, Any]]:
        """§4.4.1: 跨会话历史保留最近一轮 tool 交互(以 tool 结尾的形态)。

        背景:tool 消息缺 tool_call_id 与 tool_calls 字段(当前 schema 只存 content),
        若全部重放会破坏 OpenAI tool_calls 协议触发 API 报错;
        本方法仅在历史以 tool 结尾时,保留该 tool 及其配对的 assistant,
        让 LLM 知道上一轮调过什么工具。

        注意:在 `assistant → tool → assistant` 的常见形态下,算法仍会丢弃中间的
        tool(因为末尾是 assistant,会重置 last_round_start 到末尾 assistant)。
        这是保守安全选择,避免孤立的 tool 触发 API 400。上下文连续性由
        `short_memory` 摘要补偿(参见 agent_core.agents.hub.format_subagent_start)。
        其余轮次的 tool 始终丢弃,仅保留 user/assistant/system。
        """
        msgs = await self.memory.list_recent_messages(session_id, limit=limit)
        out: list[dict[str, Any]] = []
        # 1. 反向扫描,定位"以 tool 结尾的最近一轮"起点;若末尾非 tool 则取末尾 assistant
        last_round_start = len(msgs)  # 默认 = len,即不保留任何 tool
        for idx in range(len(msgs) - 1, -1, -1):
            m = msgs[idx]
            if m.role == "tool":
                # 最后一条是 tool: 回溯找配对的 assistant
                for j in range(idx, -1, -1):
                    if msgs[j].role == "assistant":
                        last_round_start = j
                        break
                break
            if m.role == "assistant":
                # 最后一条是 assistant: tool 已被消费或不存在(无需保留旧 tool)
                last_round_start = idx
                break
        # 2. 正向输出(保持原始时间顺序)
        for idx, m in enumerate(msgs):
            if m.role in ("user", "assistant", "system"):
                out.append({"role": m.role, "content": m.content or ""})
            elif m.role == "tool" and idx >= last_round_start:
                # tool 仅保留最近一轮(配对的 assistant+tool)
                out.append({"role": "tool", "content": m.content or ""})
        return out
    def context_segments(
        self, messages: list[dict[str, Any]], agent_id: str
    ) -> list[dict[str, Any]]:
        """用于 context-window 统计。"""
        system_tokens = 0
        msg_tokens = 0
        for m in messages:
            t = MemoryService.estimate_tokens(m.get("content") or "")
            if m.get("role") == "system":
                system_tokens += t
            else:
                msg_tokens += t
        tools = global_registry.get_tools_for_agent(agent_id)
        tool_tokens = MemoryService.estimate_tokens(
            json.dumps([t.name for t in tools])
        )
        return [
            {"label": "System / Soul", "tokens": system_tokens, "kind": "system"},
            {"label": "对话消息", "tokens": msg_tokens, "kind": "messages"},
            {"label": "工具定义", "tokens": tool_tokens, "kind": "tools"},
            {
                "label": "记忆",
                "tokens": max(0, system_tokens // 4),
                "kind": "memory",
            },
        ]

    @staticmethod
    def _format_profile(profile: dict) -> str:
        """默认不注入完整画像；仅提示称呼 + 按需工具。"""
        if not profile:
            return (
                "（暂无本机身份信息）\n"
                "需要称呼、语言、技术栈、兴趣等时，调用 get_learner_info(fields=[...])。"
            )
        identity = profile.get("identity") or {}
        if not isinstance(identity, dict):
            identity = {}
        name = (identity.get("preferred_name") or "").strip()
        name_line = f"称呼: {name}" if name else "称呼: （未设置，可请用户在个人主页填写）"
        return "\n".join(
            [
                name_line,
                "完整信息默认不注入。需要时调用 get_learner_info，"
                "fields 仅包含当前必要字段，例如 "
                '["preferred_name","tech_stack","programming_languages"]。',
                "可用字段: preferred_name, spoken_languages, programming_languages, "
                "tech_stack, interests, occupation, experience_level, bio, "
                "learning_preferences, tech_proficiency, goals, history_summary。",
            ]
        )

    @staticmethod
    def _format_memory_items(items: list[dict]) -> str:
        if not items:
            return "（暂无长期记忆）"
        lines = []
        for it in items[-15:]:
            if isinstance(it, dict):
                content = it.get("content") or it.get("value") or ""
                conf = it.get("confidence", "")
                lines.append(f"- {content} (confidence={conf})")
        return "\n".join(lines) if lines else "（暂无）"

    @staticmethod
    def _format_short(items: list[dict]) -> str:
        if not items:
            return "（暂无）"
        lines = []
        for it in items[-8:]:
            if isinstance(it, dict):
                lines.append(f"- {it.get('summary') or it.get('content') or it}")
        return "\n".join(lines)
