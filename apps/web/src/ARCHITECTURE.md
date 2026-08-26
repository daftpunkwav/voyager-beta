# Voyager 前端架构(apps/web)

> 与 `docs/architecture.md` §2.1 / §10.1 / §12 严格对齐。本文件记录**当前实施**与
> **目标态**的差异,以及迁移路径。

## 1. 共享物(铁律 1 前端落实)

全应用唯一的共享层只有 3 个:

| 共享层 | 路径 | 作用 |
|---|---|---|
| **bridge** | `src/bridge/` | 唯一与后端对话的层;所有 capability 调用、事件流订阅、共享 chatStore 走这里 |
| **contracts** | `src/api/types.ts` | 纯类型(从 `platform/contracts/` 同步);新代码禁止用兼容层 `getApi()` |
| **基础 UI 包** | `src/components/common/` `src/components/layout/` `src/components/icons/` | ToastContainer / GlassCard / EmptyState / LoadingSpinner / Sidebar / Topbar / NavIcons 等跨域通用 UI |

**禁止**:
- 页面之间共享私有 component / store / hook(共享只能经 `bridge/contracts/基础 UI 包`)
- 页面之间互 import(`pages/A/*` 不允许 `import from '@/pages/B/*'`,ESLint `no-restricted-imports` 强制)
- 页面直接 `@/api/real`(`api/real/` 已删除,旧路径解析为 `getApi()` 兼容入口,见 §3)
- `components/<domain>/` 子目录的组件跨 page 共享(当前迁移期允许,见 §4)

## 2. 当前目录结构(域内聚)

```
apps/web/src/
├── api/                # 兼容入口(老 store 仍调 getApi());新代码走 bridge
│   ├── client.ts       # getApi() → legacyApi.IApiClient;clearLegacyTokenStorage
│   └── types.ts        # 完整领域类型(User/Project/Note/GraphNode/...);IApiClient 类型
│
├── bridge/             # ★ 唯一与后端对话层(全应用唯一)
│   ├── client.ts       # callCapability<T>(domain, name, args) — §2.1 一份 Action 模型
│   ├── activity.ts     # 活动上报 / 隐私开关
│   ├── chatStore.ts    # 共享 chat 状态(浮动窗与主页同源)
│   ├── events.ts       # 事件类型定义
│   ├── feed.ts         # 事件流(用于 ActivityPage)
│   ├── legacyApi.ts    # ★ 兼容层:84 方法 IApiClient,全部走 callCapability
│   ├── pageContext.ts  # 页面感知协议
│   └── stream.ts       # 共享 SSE / EventSource
│
├── components/         # 基础 UI 包 + 单域组件
│   ├── common/         # 跨域基础 UI(ToastContainer/GlassCard/EmptyState/ConfirmDialog/LoadingSpinner/MarkdownRenderer/MermaidBlock/ErrorBoundary/GlassSelect)
│   ├── layout/         # 跨域壳组件(Sidebar/Topbar — 已被 shell/AppShell 使用)
│   ├── icons/          # NavIcons 跨域 icon 字典
│   ├── agent/          # 单域(agent)组件(迁移期共享 — 见 §4)
│   ├── code-graph/     # 单域组件
│   ├── graph/          # 单域组件
│   ├── note/           # 单域组件
│   ├── project/        # 单域组件
│   ├── settings/       # 单域组件(含 llm 子目录)
│   ├── usage/          # 单域组件
│   └── avatars/        # (空,占位)
│
├── constants/          # 跨域只读常量
│
├── hooks/              # ★ 单域 1:1 映射 — 0 跨域、0 循环(本审查 grep 验证)
│   ├── useAuth.ts          → stores/authStore
│   ├── useCodeGraph.ts     → stores/codeGraphStore
│   ├── useGraph.ts         → stores/graphStore
│   ├── useNotes.ts         → stores/noteStore
│   ├── useOverview.ts      → (聚合,跨域只读)
│   ├── useOverviewMockRoundSync.ts
│   ├── useProjects.ts      → stores/projectStore
│   ├── useSettings.ts      → stores/settingsStore
│   ├── useTheme.ts         → stores/uiStore
│   └── useTrendingScoutSpot.ts
│
├── pages/              # ★ 页面即模块(§10.1 铁律 1 落实)
│   ├── activity/ActivityPage.tsx    + provider.ts
│   ├── agent/AgentPage.tsx          (原 /)
│   ├── code-graph/CodeGraphPage.tsx
│   ├── graph/GraphPage.tsx
│   ├── health/HealthPage.tsx
│   ├── notes/NotesPage.tsx
│   ├── overview/OverviewPage.tsx
│   ├── settings/SettingsPage.tsx
│   ├── sources/ProjectsPage.tsx     + ProjectDetailPage.tsx
│   ├── team/TeamPage.tsx            + provider.ts
│   └── usage/UsagePage.tsx
│
├── shell/              # 应用壳
│   ├── AppShell.tsx    # Sidebar + Topbar + ToastContainer + ServiceBadges + PageProbe + FloatingChat
│   ├── Degraded.tsx
│   ├── ServiceBadge.tsx
│   └── useTheme.ts     # 全局主题 hook
│
├── stores/             # ★ 0 跨域互引(本审查 grep 验证)
│   ├── agentStore.ts   + sseHandlers 子目录
│   ├── authStore.ts
│   ├── codeGraphStore.ts
│   ├── graphStore.ts
│   ├── noteStore.ts
│   ├── projectStore.ts
│   ├── settingsStore.ts
│   └── uiStore.ts
│
├── styles/             # 设计系统(单一来源)
│   ├── design-system.css   # 1236 行 — Voyager v1.0 设计系统(中性命名)
│   ├── liquid-glass.css    # 496 行 — 液态玻璃子系统
│   ├── shell.css / global.css
│   └── pages/              # 页面私有 CSS(可被 page 目录迁移时吸收)
│
├── utils/              # 跨域纯函数工具
│
├── widgets/            # 浮动窗 / 页面感知 / 转发 stub
│   ├── FloatingChat.tsx    # 常驻悬浮对话(§10.12)
│   ├── PageProbe.tsx       # 页面感知(§5.1 / §9.20)
│   ├── probes.ts           # 路由 → page provider 映射
│   ├── chat/               # AskDialog + MessageList
│   ├── ConfirmDialog.tsx   # 转发到 components/common
│   ├── EmptyState.tsx      # 转发到 components/common
│   ├── GlassCard.tsx       # 转发到 components/common
│   └── LoadingSpinner.tsx  # 转发到 components/common
│
├── App.tsx             # 路由表(13 路由)
├── main.tsx            # 入口:StrictMode + QueryClientProvider + BrowserRouter
└── ARCHITECTURE.md     # 本文件
```

## 3. 兼容层(legacyApi)与新代码契约

**关键事实**:`getApi()` 不违反"一份 Action 模型"(铁律 2)。

- `bridge/legacyApi.ts` 是**兼容入口**,84 个方法内部全部走 `callCapability`
- 旧 store / hook 因为历史原因仍用 `getApi()`,功能上等价于 `callCapability`
- **新代码必须用 `callCapability`**(`api/client.ts` 头注释已显式禁止)
- ESLint `no-restricted-imports` 在审查中可选启用(目前未启用,避免误伤旧 page)

**过渡期时间表**:
- 当前:旧 page 用 `getApi()`(经 legacyApi 桥接),新 page 用 `callCapability`
- 目标:所有 page → `callCapability`;`legacyApi.ts` 删除(由 `bridge/chatStore` / `bridge/stream` 接管实时能力)

## 4. 迁移期 vs 目标态(§10.1)

### 4.1 当前(迁移期)

- 9 个 page 来自 RepoPilot 上游,`components/<domain>/` 子目录的组件**跨 page 共享**
  - 例如:`components/agent/ChatPanel.tsx` 被 `AgentPage` 使用,`components/note/NoteList.tsx` 被 `NotesPage` 使用
  - 共享本身**不违反**铁律 1(单域内聚),但 §10.1 严格说应该是"页面私有"
- `@ts-nocheck` 标注 33 个旧 file + 3 个上游 code-graph file(全部带说明)
- 4 个新 page(ActivityPage / TeamPage / HealthPage / 早期 ChatPage)严格
- 旧 `localStorage` key 改 `voyager_*` 中性化

### 4.2 目标态(§10.1)

每个 page 目录自包含:
```
pages/<domain>/
├── <Domain>Page.tsx
├── components/      # 页面私有
├── hooks/
├── store/
└── provider.ts      # PageProbe 摘要
```

`components/<domain>/` 子目录整体下沉到 `pages/<domain>/components/`,消除跨 page 共享。

**不在本批次范围**:RepoPilot 上游代码完整迁移需要拆分 30+ component / 9 个 page,
工作量大且影响布局 CSS 路径;留作未来重构任务。

## 5. 域内聚映射(本审查 grep 验证)

| Page | Domain | 跨域只读(聚合) |
|---|---|---|
| `agent/AgentPage` | agent | `useUIStore` |
| `team/TeamPage` | team | `useAgentStore`(读人格) |
| `notes/NotesPage` | note | `useUIStore` + `useProjects`(源选择) |
| `sources/ProjectsPage` | source | `useUIStore` + `useProjectStore` |
| `sources/ProjectDetailPage` | source | `useUIStore` + `useNoteStore` + `useCodeGraph` + `useGraph` |
| `graph/GraphPage` | graph | `useUIStore` + `useGraphStore` + `useGraph` |
| `code-graph/CodeGraphPage` | code-graph | `useUIStore` + `useCodeGraphStore` |
| `overview/OverviewPage` | overview | `useAuthStore` + `useUIStore` + `useOverview` + `useTrendingScoutSpot` |
| `activity/ActivityPage` | activity | `useUIStore` |
| `health/HealthPage` | system.health | `useUIStore` |
| `usage/UsagePage` | usage | `useUIStore` |
| `settings/SettingsPage` | settings | `useUIStore` + `useSettings` + `useTheme` + `useProjects`(GitHub 账号) |

**所有 page 单向消费其他域** — 没有任何 page 写其他域的 store,无循环。

## 6. ESLint 规则(本审查新增)

`apps/web/eslint.config.js` 在 `pages/**/*.tsx` 上启用:

```js
'no-restricted-imports': ['error', {
  patterns: [{
    group: ['@/pages/*'],
    message: '页面之间互不 import(§10.1 铁律 1);共享物只能经 bridge/contracts/基础 UI。',
  }, {
    group: ['@/api/real', '@/api/real/*'],
    message: '@/api/real 已删除;旧调用应改用 getApi()(经 legacyApi 桥接)或 callCapability(新代码)。',
  }],
}]
```

旧 page 标 `@ts-nocheck` 跳过此规则(已知);新 page 与重构后的 page 受强制。

## 7. 命名中性(§13.3)

- 工作区全量 grep `'RepoPilot' | 'repo-pilot' | 'rp-ui-store' | 'rp_token' | 'rp_session' | 'rp_agent_*'` = **0 命中**
- `localStorage` key:全部 `voyager_*` 前缀
- `persist({ name: 'voyager-ui-store' })` 中性化
- 路由命名:`/sources` (资源库) `/team` (团队) `/activity` (活动) `/system/health` (服务健康)
- 旧 page 内部仍引用"project_id"等字段(由 `legacyApi` 边界归一化);目标态是 `source_id`
