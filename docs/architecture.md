# Voyager 架构设计(最终形态)

> **本文档描述 Voyager 的最终形态设想**:读完它,应当能回答——项目是什么、有哪些功能、
> 用户在前端能看到什么/能做什么、agent 如何组织与执行、模块如何划分与通信、
> 权限/记忆/上下文如何设计、目录如何组织、每个模块的边界在哪里、坏了怎么表现。
> 本文档不含具体实现代码,但包含全部架构与设计决策。§15 记录所有已拍板的决策。

---

## 目录

- §1 项目定位与愿景
- §2 设计哲学与铁律
- §3 并发模型:多进程还是多线程
- §4 总体架构
- §5 完整目录结构
- §6 模块清单与职责边界
- §7 横切设施(platform)
- §8 领域服务(services)
- §9 Agent Runtime 详设
- §10 前端信息架构
- §11 示例场景(端到端)
- §12 依赖矩阵
- §13 工程规约(独立开发、文件级脱耦、命名中性)
- §14 演进路线
- §15 决策记录(已定稿)

---

## 1. 项目定位与愿景

**Voyager 是一个本地优先、单用户的"agent 共生工作台"**:人和 agent 是同一系统里
地位同等的两类行动者(actor),共享同一份数据、同一套能力、同一条事件流。

三大业务场景:

1. **学习与了解**:导入 GitHub 项目、书籍、新闻,agent 建立索引与知识图谱,
   串讲、出题、陪读;图谱把一切知识串联成可探索的结构。
2. **办公**:应用内直接编辑 Word/PPT 类文档;agent 知道你的鼠标指在哪里、
   选中了什么,可以就地改、按指令改;可以把新闻/资料自动整理成文档。
3. **编码**:指定路径在真实环境或容器沙箱中运行代码,提供常见语言环境,
   即指即跑,结果回灌对话与笔记。

贯穿三者的主线:**agent 拥有自己的生命**。它有自己的常驻 runtime、自己的
工作目录、自己的记忆、自己的权限边界;它不因用户输入才工作——它观察事件流,
会在你上线时主动打招呼,在你搬书的时候主动搭把手;它常驻在屏幕角落的悬浮窗里,
知道你在哪一页、正指着什么。

**命名中性**:Voyager 只是暂用名。目录、文件、变量、函数、包名、配置键
一律按**功能/职责/边界**取中性名(如 `gateway`、`eventbus`、`workspace`),
代码中不出现品牌名;品牌字符串只存在于品牌配置文件一处,改名只动这一处(§13.3)。

## 2. 设计哲学与铁律

### 2.1 八条铁律

1. **全层级脱耦**:脱耦作用于四个层级——
   - *服务之间*:只允许三种通信——capability 调用、事件流、契约包(纯类型)。
     禁止跨服务 import 实现、共享可变内存、读写别人的数据表;
   - *服务内部*:聚合服务的子模块之间同样只经内部注册表组合,互不 import(§8.2、§8.6);
   - *前端*:页面即模块,页面私有组件/状态不共享,共享物只有三个——
     bridge、contracts、基础 UI 包(§10.1);
   - *文件*:一个文件一个职责;按业务内聚组织目录,而不是按类型堆叠
     (不许出现一个什么都往里塞的 `utils.py` / `misc/`)。
2. **一份 Action 模型**:能力(capability)只定义一次(schema + handler + 元数据),
   REST 路由与 MCP tools 均从注册表生成,永不手写第二份。
3. **一切皆事件**:用户消息、行为观察、任务进度、agent 发言、定时器、
   服务健康变化——都是同一条事件流上的事件。用户输入只是事件的一种。
4. **数据库即协调层**:人与 agent 读写同一份状态;UI 订阅事件刷新,agent 订阅事件感知世界。
5. **服务即 runtime**:每个领域服务是独立可运行的进程,谁拥有领域,谁拥有它的队列与调度。
   **单服务故障只影响自己**(§7.10)。
6. **权限即工具面**:不给 subagent 写权限的方式是"不授予 write 工具",
   而不是"在提示词里说你不能写"。一切权限在 capability 入口强制校验,不靠口头约束。
7. **Parity(对等),隐私除外**:用户能在应用里做的,agent 经同一 capability 也能做——
   **唯一例外是隐私项**(API key 等 secret,只有用户本人可写,见 §8.8)。
   agent 做的一切在 UI 可见、可查、可撤销。Parity 成立的必要条件:
   状态落在共享基座 + 能力收进注册表;客户端外壳(chrome)的私有状态不参与 parity。
8. **命名中性**:目录、文件、变量、函数、包名、配置键一律按功能/职责/边界命名;
   代码内不出现品牌名(§1、§13.3)。

### 2.2 为什么把脱耦推到文件级

本项目的功能面会持续增长(学习 → 办公 → 编码 → 更多未知领域)。脱耦不是洁癖,
是扩展性的前提:服务间脱耦 → 新领域是新增目录;服务内脱耦 → 聚合服务可以
容纳"仓库/书籍/新闻/未来类型"而不变成大泥球;前端脱耦 → 页面可独立开发;
文件级脱耦 → 每个文件可被单独理解、测试、替换。代价是更多小文件,
收益是任何改动的影响半径都可预测。

### 2.3 Parity 的边界与设置的能力化

判断新功能归属的标准问题:**希望 agent 也能做它吗?**
希望 → 领域数据 + capability;不希望(窗口位置、悬浮窗坐标等纯客户端体验) →
留在 chrome。**设置也是能力**:每个服务自带设置注册表(§8.1),
用户能改的设置 agent 都能改——除了标记为 `secret` 的项(§8.8)。
同时防止低层旁路:agent 技术上能读共享基座的文件,但一切变更必须过注册表——
共享基座的可达性不等于操作的合法性。

## 3. 并发模型:多进程还是多线程

### 3.1 结论

**多进程为骨架,进程内 asyncio + 进程池为肌理。** 领域服务、agent runtime、
gateway 各自是独立进程;进程内部用 asyncio 事件循环处理 IO 并发,
CPU 密集任务(索引、布局计算、文档渲染、容器内执行)扔到进程池/子进程/容器。

### 3.2 对比分析

| 维度 | 多线程(单进程) | 多进程(选定) |
|---|---|---|
| 故障隔离 | 差:索引崩溃可能拖垮对话 | 好:单个服务崩溃不影响其余(§7.10) |
| Python GIL | CPU 密集互相卡死 | 天然绕过,真并行 |
| 独立重启/升级 | 不可能 | 重启 graph 服务,对话不中断 |
| 耦合风险 | 共享内存 → 隐式耦合,违反铁律 1 | 只能经协议通信,脱耦被结构强制 |
| 微服务演进 | 需要重拆 | 进程边界即服务边界,平移即可 |
| 资源占用 | 低 | 略高(每进程一份解释器),本地可接受 |
| 调试便利 | 单进程好调 | 提供"单体模式"弥补(见下) |

### 3.3 单体模式(开发档)

保留一个"单体模式":所有服务以库形式挂进同一个进程,**接口与协议完全不变**
(调用仍走注册表与事件流,只是传输从 IPC 换成本地函数)。用于一键开发调试。
它是部署形态,不是架构豁免——单体模式下同样禁止跨模块 import 实现,
CI 用依赖检查(§12)强制保证。

### 3.4 进程内并发

- IO(LLM 调用、HTTP、DB)一律 asyncio;
- CPU 密集(布局、仓库解析、文档渲染)进进程池,事件循环永不阻塞;
- 长任务一律 `job_id + 事件/进度通知`,任何调用方不得同步阻塞等待;
- agent 的 subagent 是**进程内的轻量决策实例**(asyncio task 级),
  不是进程——进程隔离留给领域服务,决策并发留给事件循环(§9.4.5)。

## 4. 总体架构

```
                          ┌──────────── 人类 ────────────┐
                          │   apps/web    apps/desktop    │
                          └──────┬─────────────────┬─────┘
                            REST/SSE        行为上报/AskUser 应答/上线事件
                                 ▼                 ▼
                     ┌─────────────────────────────────────┐
                     │  gateway(对人类的唯一聚合入口)        │
                     │  鉴权·限流·审计·chat 通道·SSE·设置聚合 │
                     │  健康探测与统一错误码(§7.10)          │
                     └──────┬──────────────────────┬───────┘
                            │ capability 调用       │ 投递事件
                            ▼                      ▼
   ┌──────────────────────────────┐     ┌──────────────────────────┐
   │ services/*(领域服务集群)      │────▶│  事件流(持久化事件日志)   │
   │ sources·notes·graph·office·  │ pub  └────────────┬─────────────┘
   │ code-exec·browser·llm·       │                   │ sub
   │ settings                     │        ┌──────────▼─────────────┐
   └──────▲───────────▲──────────┘        │  agent(常驻 runtime)    │
          │           │                   │  Lucien(master)·observe· │
          │           └──MCP(stdio/HTTP)──┤  subagent 集群·policy·   │
          │              capability 调用   │  memory·skills·hooks·    │
          │                               │  proactive(主动触达)     │
          │                               └──────────▲─────────────┘
          │                                          │ spawn/监督
   外部 MCP client ──▶ 各服务的 mcp_server(对外暴露同一注册表)
```

分层说明:

- **apps 层**:渲染与采集。不直连任何领域服务,一切经 gateway。
- **gateway 层**:对人类的适配器聚合。零业务逻辑:协议转换、鉴权、限流、审计、
  chat 通道、**各服务设置的聚合读取**(§8.8)、**服务健康探测与统一错误码**(§7.10)。
- **services 层**:领域能力本体。每个服务独立进程,自带队列与调度,
  同时暴露 REST(经 gateway)与 MCP(给 agent 与外部 client)。
- **agent 层**:系统内唯一的"决策者"。读事件流,决定说/做/沉默;
  不直接写任何业务库表,只调 capability;**agent 自己也暴露 capability**
  (读/改自身设置、查记忆、查任务),与用户同权。
- **platform 层**:横切设施库,唯一被所有模块依赖,只含机制、不含业务。

---

## 5. 完整目录结构

> 顶层八个目录:`apps / agent / services / platform / plugins / workspace / docs / runtime-data`。
> 命名全部按功能/职责/边界,不含品牌名。每个目录有自述 README,与其模块卡(§6)一致。
> **注意:本树与 §8 列出的能力/文件均为"初始最小集",不封闭**——各领域的完整能力
> 设计(如图谱的全部工具)在 `docs/modules/<domain>.md` 模块卡中详细设计与持续演进;
> 新增能力只改对应服务的注册表与模块卡,不需要改本文档。

```
voyager/                              # 仓库根(目录名即功能名)
│
├── apps/                             # 人类入口:渲染与采集,不含业务逻辑
│   ├── web/                          # Web 端(React + Vite)
│   │   ├── src/
│   │   │   ├── main.tsx              # 入口:只挂载 shell,不含任何业务
│   │   │   ├── shell/                # 应用壳:导航、路由、全局组件挂载点
│   │   │   │   ├── index.tsx         #   壳布局:导航栏 + 页面容器 + 全局层
│   │   │   │   ├── nav.tsx           #   导航定义:Agent 域 / 领域域 / 系统域(§10.1)
│   │   │   │   ├── router.tsx        #   路由表;agent.navigate 指令在此落地
│   │   │   │   ├── floating-chat.tsx #   ★ 常驻悬浮对话窗(气泡/展开两态,§10.12)
│   │   │   │   ├── global-widgets.tsx#   AskUser 弹窗、确认卡片、kill switch 挂载
│   │   │   │   └── service-badge.tsx #   服务健康徽章(订阅 service.health.changed)
│   │   │   ├── pages/                # ★ 页面即模块:自包含五件套,页面间互不 import
│   │   │   │   ├── chat/             #   Agent Chat(默认首页)
│   │   │   │   │   ├── index.tsx     #     页面入口:只做组件组装
│   │   │   │   │   ├── provider.ts   #     页面上下文提供者:输出页面摘要(§9.20)
│   │   │   │   │   ├── store.ts      #     页面私有状态
│   │   │   │   │   ├── hooks.ts      #     页面私有逻辑
│   │   │   │   │   └── components/   #     页面私有组件(不外借)
│   │   │   │   │       ├── message-list.tsx    # 消息流(含人格头像)
│   │   │   │   │       ├── input-box.tsx       # 输入框(插话/模式切换)
│   │   │   │   │       ├── task-card.tsx       # 任务进度卡片
│   │   │   │   │       ├── preview-card.tsx    # 产物快速预览卡片(§10.2)
│   │   │   │   │       └── subagent-badge.tsx  # 运行中 subagent 徽章
│   │   │   │   ├── sources/          #   资源库(五件套同构;组件:resource-list /
│   │   │   │   │                     #     import-dialog / reader / degraded)
│   │   │   │   ├── notes/            #   笔记(note-list / md-editor / degraded)
│   │   │   │   ├── graph/            #   图谱(graph-canvas / queue-panel /
│   │   │   │   │                     #     node-detail / engine-badge / degraded)
│   │   │   │   ├── studio/           #   工坊(doc-editor / slides-editor /
│   │   │   │   │                     #     code-runner / degraded)
│   │   │   │   ├── overview/         #   总览(摘要卡片组)
│   │   │   │   ├── activity/         #   活动(feed / filters / undo)
│   │   │   │   ├── usage/            #   用量(统计图表)
│   │   │   │   ├── agents/           #   Agent 团队(persona-card / instance-card /
│   │   │   │   │                     #     create-subagent-dialog)
│   │   │   │   └── settings/         #   设置(settings-renderer:按 schema 动态渲染)
│   │   │   ├── bridge/               # 唯一与后端对话的层(全应用唯一)
│   │   │   │   ├── api.ts            #   REST client(只指向 gateway)
│   │   │   │   ├── stream.ts         #   SSE:agent 消息流 + 任务进度
│   │   │   │   ├── activity.ts       #   行为上报(节流 + 隐私开关 + 上线/指针事件)
│   │   │   │   └── errors.ts         #   统一错误码 → 提示文案(§7.10)
│   │   │   └── contracts/            # 从 platform/contracts 生成的 TS 类型(只读)
│   │   └── tests/                    # 页面级测试(每页面目录内自带)
│   └── desktop/                      # 桌面端(Electron,决策 §15)
│       ├── shell/                    # 壳:窗口、托盘、自动更新、进程监督
│       ├── file-bridge/              # 本地文件对话框/拖拽桥接
│       └── browser-host/             # 浏览器自动化宿主(§8.7)
│
├── agent/                            # Agent Runtime:常驻进程,系统的决策者
│   ├── main.py                       # 进程入口:起事件循环、连事件流、服务发现
│   ├── runtime/                      # 运行时底座(§9.1 十二职责)
│   │   ├── loop.py                   #   事件循环:取事件 → 分发 → 行动/沉默
│   │   ├── scheduler.py              #   调度:subagent 生命周期、并发、优先级、
│   │   │                             #     一次性定时器(追问用,§9.8)
│   │   ├── state.py                  #   状态:run/step/plan/tool_results/checkpoint
│   │   ├── recovery.py               #   容错:重试/backoff/熔断/checkpoint/resume
│   │   ├── events.py                 #   runtime 级事件(RunStarted/ToolFailed…)
│   │   └── observability.py          #   trajectory、token/成本计量、日志
│   ├── master/                       # 主 agent Lucien(强制 ReAct,§9.4.2)
│   │   ├── master.py                 #   统筹:任务分解、派单、监督、汇总
│   │   ├── arbiter.py                #   消息仲裁:排队(默认)/自动/引导(§9.7)
│   │   ├── digest.py                 #   摘要器:维护 subagent 状态卡片(§9.6)
│   │   └── proactive.py              #   主动触达引擎:问候/追问/预算熔断(§9.8)
│   ├── personas/                     # 人格预设(纯数据:名字/风格/能力面模板/默认模式)
│   │   ├── lucien.py                 #   统筹者(唯一常驻)
│   │   ├── iris.py                   #   侦察检索
│   │   ├── elio.py                   #   讲解导师
│   │   ├── miyai.py                  #   策展整理
│   │   └── atlas.py                  #   图谱向导
│   ├── subagent/
│   │   ├── spawn.py                  #   派出:能力面裁剪 + 模式授予(§9.4)
│   │   ├── instance.py               #   实例:一次运行的状态机
│   │   ├── modes.py                  #   七种模式的执行策略实现(ReAct/GoT/…)
│   │   └── registry.py               #   用户自建 subagent 的注册与加载(§9.4.4)
│   ├── policy/
│   │   ├── engine.py                 #   权限引擎:四维权限判定(§9.9)
│   │   └── levels.py                 #   行动分级:L0 静默 / L1 提示 / L2 确认
│   ├── memory/
│   │   ├── profile.py                #   用户画像与偏好
│   │   ├── episodic.py               #   情节记忆:决策留痕(保留策略 §9.11)
│   │   ├── semantic.py               #   语义记忆:与图谱联动
│   │   └── working.py                #   工作记忆:当前会话
│   ├── context/
│   │   ├── builder.py                #   上下文装配:规则→人格→画像→任务书→摘要
│   │   ├── compressor.py             #   压缩/剪枝/重建(§9.12)
│   │   └── loader.py                 #   ★ 按需加载器:skill/记忆/页面上下文(§9.20)
│   ├── skills/
│   │   ├── loader.py                 #   skill 索引常驻 + 全文按需(§9.20)
│   │   └── organizer.py              #   自动整理:发现重复流程 → 提议入库(§9.13)
│   ├── hooks/
│   │   ├── loader.py                 #   hook 加载
│   │   └── triggers.py               #   钩子点触发(事件/工具前后/生命周期)
│   ├── tools/                        # agent 自身工具(不经领域服务):
│   │   ├── ask_user.py               #   询问用户(§9.15)
│   │   ├── request_context.py        #   向 master 申请上下文(§9.6)
│   │   ├── spawn_subagent.py         #   派出 subagent
│   │   ├── reach_out.py              #   主动发消息(fire-and-forget,§9.8)
│   │   ├── load_skill.py             #   按需读 skill 全文(§9.20)
│   │   ├── recall_memory.py          #   检索式记忆查询(§9.20)
│   │   ├── fs.py                     #   文件读写(经 fs jail + policy)
│   │   ├── shell.py                  #   命令执行(经 policy)
│   │   └── web.py                    #   搜索/抓取(经网络权限层)
│   ├── capabilities.py               # ★ agent 自己也暴露能力:读/改 agent 设置、
│   │                                 #   查记忆、查任务……经 gateway 与用户同权
│   ├── settings.py                   # agent 自身设置项(轮数/仲裁默认/触达预算…)
│   └── clients/
│       ├── pool.py                   #   各服务的 MCP client 连接池
│       └── discovery.py              #   服务发现 + 动态 list_tools(§9.4)
│
├── services/                         # 领域服务集群:每个目录 = 一个独立进程
│   ├── _template/                    # 新领域脚手架(六件套 + tests,§8.1)
│   ├── sources/                      # ★ 资源聚合服务(仓库/书籍/新闻,§8.2)
│   │   ├── capabilities.py           #   聚合注册表:仅合并各子模块注册表,零逻辑
│   │   ├── rest.py                   #   聚合注册表 → FastAPI router
│   │   ├── mcp_server.py             #   聚合注册表 → FastMCP server
│   │   ├── worker.py                 #   聚合调度:按资源类型分发到子模块队列
│   │   ├── settings.py               #   服务级设置项(默认排序、导入并发…)
│   │   ├── service.json              #   模块卡:名称、端口、能力清单、订阅事件
│   │   ├── tests/
│   │   └── modules/                  #   ★ 子模块间互不 import(服务内脱耦)
│   │       ├── _template/            #     新资源类型复制即用
│   │       ├── repo/                 #     GitHub 仓库(自包含)
│   │       │   ├── capabilities.py   #       import_repo / list_repos / …(初始集)
│   │       │   ├── store.py          #       本类型的表与访问
│   │       │   └── worker.py         #       clone/解析队列
│   │       ├── books/                #     书籍(同构三件套)
│   │       └── news/                 #     新闻(同构三件套)
│   ├── notes/                        # 笔记服务(六件套;仅 Markdown,§8.3)
│   ├── graph/                        # 图谱服务(§8.4;能力为初始集,详见模块卡)
│   │   ├── capabilities.py           #   注册表:enqueue/cancel/reorder +
│   │   │                             #   set_node/set_relationship/query…(不封闭)
│   │   ├── pipelines/                #   ★ 两条建图管线(互不 import)
│   │   │   ├── code/                 #     程序化:源码分析 + 仓库关联度分析
│   │   │   │   ├── analyze.py        #       源码解析 → 节点/边
│   │   │   │   └── relate.py         #       仓库间关联度计算
│   │   │   └── ai/                   #     AI 建图:agent 经 set_node/set_relationship
│   │   │       └── guide.py          #       建图引导(给 agent 的建图约定与校验)
│   │   ├── engines/                  #   ★ 引擎适配层(程序化管线的执行者)
│   │   │   ├── adapter.py            #     统一接口 + 探测/回退逻辑
│   │   │   ├── c/                    #     C 引擎(默认;sidecar 子进程)
│   │   │   └── python/               #     Python 引擎(回退;纯 Python)
│   │   ├── queue.py                  #   优先级队列:enqueue/cancel/reorder
│   │   ├── scheduler.py              #   调度:并发上限、重试、backoff
│   │   ├── store.py                  #   节点/边/嵌入存储(独立命名空间)
│   │   ├── settings.py               #   引擎选择、并发上限等设置项
│   │   ├── service.json
│   │   ├── rest.py / mcp_server.py
│   │   └── tests/
│   ├── office/                       # ★ 办公聚合服务(§8.6)
│   │   ├── capabilities.py           #   聚合注册表(同 sources 模式,零逻辑)
│   │   ├── rest.py / mcp_server.py · worker.py · settings.py · service.json
│   │   ├── tests/
│   │   └── modules/
│   │       ├── _template/            #     未来类型(sheets…)复制即用
│   │       ├── doc/                  #     Word 类文档(自包含三件套)
│   │       └── slides/               #     PPT 类演示(自包含三件套)
│   ├── code-exec/                    # 代码执行:容器沙箱(§8.5)
│   ├── browser/                      # 浏览器自动化(§8.7)
│   ├── llm/                          # LLM 提供商目录与连接管理(§8.8)
│   ├── settings/                     # 应用设置聚合(外观/仲裁/触达/隐私…,§8.8)
│   └── gateway/                      # 对 apps 的聚合入口(健康探测 + 错误码,§7.10)
│
├── platform/                         # 横切设施:唯一被所有模块依赖的库,只含机制
│   ├── contracts/                    # ★ 契约(纯类型零依赖;TS 类型由此生成)
│   │   ├── events.py                 #   全部事件类型
│   │   ├── dto.py                    #   capability 输入输出 DTO
│   │   ├── errors.py                 #   统一错误码定义(§7.10)
│   │   └── version.py                #   协议版本
│   ├── capability/                   # ★ 能力框架:一次定义 → REST + MCP 双生成
│   │   ├── define.py                 #   define_capability(装饰器与元数据)
│   │   ├── registry.py               #   注册表
│   │   ├── gen_rest.py               #   注册表 → FastAPI router
│   │   ├── gen_mcp.py                #   注册表 → FastMCP tools
│   │   └── guards.py                 #   入口强制:鉴权/限流/审计(§7.3)
│   ├── eventbus/                     # ★ 事件流:持久化事件日志 + 发布/订阅
│   │   ├── log.py                    #   追加表读写
│   │   ├── bus.py                    #   发布/订阅(进程内直推 + 跨进程游标)
│   │   └── cursor.py                 #   游标管理(恢复与重放)
│   ├── actor/                        # actor 模型、凭证、鉴权(§7.4)
│   ├── limit/                        # 限流与配额(§7.5)
│   ├── audit/                        # 审计日志(§7.6)
│   ├── observability/                # 结构化日志、trace_id、指标
│   ├── health/                       # ★ 健康探测、错误码、进程监督(§7.10)
│   ├── config/                       # 配置加载约定(§7.7)
│   ├── secrets/                      # 密钥保管(§7.7;secret 设置项的唯一写入口)
│   └── settings/                     # 设置项框架:schema/默认值/secret 标记/变更事件(§7.9)
│
├── plugins/                          # 用户插件:每个插件一个子目录
│   └── <plugin>/                     #   声明式,不 import 平台实现(§9.13)
│       ├── plugin.json               #     清单:名称、版本、权限请求、包含物
│       ├── skills/                   #     插件带入的 skill
│       ├── hooks/                    #     插件带入的 hook
│       └── mcp.json                  #     插件带入的外接 MCP server 配置
│
├── workspace/                        # Agent 默认工作目录(§9.10)
│   ├── repo/                         #   agent 克隆的 GitHub 项目
│   ├── books/                        #   书籍
│   ├── news/                         #   新闻与抓取资料
│   ├── exports/                      #   agent 生成的 Word/PPT 等产物
│   ├── imports/                      #   用户导入文件的副本
│   └── sandbox/                      #   代码执行的容器挂载目录
│
├── runtime-data/                     # 运行期数据("它的脑",与 workspace"它的家"分离)
│   ├── events.db                     #   事件日志(事件流的持久化)
│   ├── audit.db                      #   审计
│   ├── memory/                       #   agent 记忆库(四类记忆)
│   ├── checkpoints/                  #   任务断点
│   └── logs/                         #   结构化日志
└── docs/
    ├── architecture.md               # 本文档
    └── modules/                      # 每模块一张模块卡(§6 展开;各领域
                                      #   完整能力清单在此详细设计与演进)
```

## 6. 模块清单与职责边界

> 每张模块卡四项:**职责 / 不做 / 数据 / 通信**。违反任一行的改动不得合入。

### 6.1 apps/web

- **职责**:渲染 UI;采集用户行为(含指针指向、选区)并上报;SSE 接收消息流与进度;
  落地 navigate 指令;提供常驻悬浮窗与各页面的上下文提供者。
- **不做**:不直连领域服务;页面之间不共享组件与状态;不写业务规则;
  不在前端缓存全量领域数据(按需经 bridge 取,§9.20)。
- **数据**:无(本地偏好缓存除外)。
- **通信**:gateway 的 REST + SSE。

### 6.2 apps/desktop

- **职责**:Electron 壳;本地文件桥;浏览器自动化宿主(执行 browser 服务指令)。
- **不做**:不实现业务页面(复用 web 构建产物);不直连领域服务。
- **数据**:无。
- **通信**:同 web;另与 browser 服务一条受控指令通道。

### 6.3 services/gateway

- **职责**:对人类的唯一入口。鉴权、限流、审计;REST → capability 路由;
  chat 通道(投递 `user.message` + SSE 回推);行为上报与上线事件入口;
  AskUser 应答回投;聚合各服务设置 schema;**健康探测与统一错误码**(§7.10)。
- **不做**:零业务逻辑;不直接读写领域数据表。
- **数据**:无业务数据(仅鉴权/限流计数/健康快照)。
- **通信**:对下调 capability;对事件流只投递"人类侧"事件。

### 6.4 聚合服务通用卡(sources、office)

- **职责**:统一管理一组同族领域(资源类型 / 文档类型)。
- **不做**:聚合层不含任何类型逻辑——注册表只合并,worker 只做类型分发;
  子模块之间互不 import、各有自己的表与队列。
- **数据**:每子模块独立命名空间。
- **通信**:对外一个进程、一份注册表;对内纯组合。
  新增类型 = `modules/` 下新增自包含目录,聚合层零改动。

### 6.5 单一领域服务通用卡(notes/graph/code-exec/browser/llm/settings)

拥有本领域全部数据与逻辑;自带队列与调度;REST + MCP 同注册表生成;
不与其他服务互相 import;需要别的领域的数据 → 调对方 capability;
不与 LLM 直接对话(决策是 agent 的事);向 gateway 报告健康状态。各自细节见 §8。

### 6.6 agent

- **职责**:系统唯一决策者。读事件流;决定说/做/沉默;派出与监督 subagent;
  维护记忆;执行权限与分级策略;主动触达;按需在图谱上直接建节点(AI 管线,§8.4)。
- **不做**:不直接写业务库表(只调 capability);不实现领域逻辑
  (不解析代码、不排版文档——那是服务的事)。
- **数据**:记忆库、runtime 状态(checkpoint、trajectory),独立命名空间(runtime-data/)。
- **通信**:MCP client → 各服务;订阅事件流;自身工具(fs/shell/web)经 policy 层;
  对外也暴露自己的能力注册表(agent 设置、记忆查询),与用户同权。

### 6.7 platform/*

- **职责**:只提供机制,不含业务语义,不出现领域词汇与品牌名。
- **不做**:不得 import 任何 services/agent/apps。
- **数据**:定义事件日志、审计、设置项、错误码的结构;存储落 runtime-data/。
- **通信**:被所有模块作为库依赖(唯一被允许的"被依赖")。

### 6.8 plugins/

- **职责**:用户扩展的落点(§9.13)。插件 = skill + hook + MCP 配置 + UI 面板声明。
- **不做**:只声明式描述,不 import 平台内部实现。
- **数据**:插件目录内。
- **通信**:经 agent 的加载器生效。

---

## 7. 横切设施(platform)

> platform 是唯一允许被所有模块依赖的包,只含机制、不含业务、不出现领域词汇与品牌名。
> 它定义"怎么说话",从不定义"说什么"。

### 7.1 contracts(契约包)

- 内容:全部跨模块类型——事件类型、capability 的输入输出 DTO、**错误码**、协议版本号。
- 铁律:**纯类型,零逻辑,零依赖**。唯一直接被 apps / agent / services 三方引用的包。
- 前端 TS 类型由它生成,三方对同一结构的认知永远一致。
- 版本化:协议变更升版本号;多版本并存期由生成器同时产出。

### 7.2 eventbus(事件流)

- 形态:**持久化事件日志(追加表)+ 游标订阅**。进程内 asyncio 队列直推,
  跨进程走日志表。日志表同时是**审计主线与重放源**(重启从游标恢复,可重放任意区间)。
- 事件两大类:
  - **领域事件**:`user.message`、`user.online`、`user.activity`、
    `task.enqueued/progress/completed`、`agent.message`、`agent.navigate`、
    `schedule.tick`、`doc.selection.changed`、`graph.indexed`、`settings.changed`、
    `service.health.changed`……
  - **runtime 事件**(agent 内部,§9.1):`RunStarted / LLMStarted / LLMStreaming /
    LLMCompleted / ToolStarted / ToolCompleted / ToolFailed / AgentPaused /
    AgentResumed / AgentCompleted / RunFailed`。
- 每条事件必带:`id / type / actor / payload / ts / trace_id`。
- 隐私与噪音:`user.activity` 按类别白名单上报 + 节流(hover/指针防抖),
  用户在设置里按类别开关。

### 7.3 capability(能力框架)

- 一次定义:名称、描述(写给 LLM:何时用、返回什么)、输入模型、元数据
  (`cost`、`reversible`、`scopes` 所需权限)、handler。
- 双协议生成:同一注册表 → REST router(给 gateway)+ FastMCP tools(给 agent/外部)。
- 入口强制三件事(框架层,不在 handler 里):**鉴权与权限校验**(§7.4、§9.9)、
  **限流与配额扣减**(§7.5)、**审计落库**(§7.6)。
- 长任务约定:handler 只入队返回 `job_id`;进度经事件流/MCP notification;
  完成发 `task.completed`。同步长任务视为缺陷。
- 新增能力 = 注册表新增条目,REST / MCP / agent 三处零改动。

### 7.4 actor 与鉴权

- **Actor 模型**:`actor = { kind: user | agent | external, id, scopes[] }`。
  本地单用户阶段 user 恒为 `local`,结构与日志全部带 actor 字段,为多用户预留。
- **本机鉴权**:首次启动生成本机会话令牌,gateway 校验;外部 MCP client
  走 OAuth 2.1(MCP 标准)或静态令牌,按 scope 签发。
- **agent 无后门**:agent 持自己的 actor 凭证,与用户走同一套鉴权与权限校验。
- **凭证传递**:跨服务调用沿链传递 `ActorContext(actor, scopes, trace_id)`,
  任何环节不得提权。

### 7.5 限流与配额

四层,各自独立配置(都是设置项,§8.8;用户与 agent 均可改非 secret 项):

| 层 | 位置 | 内容 |
|---|---|---|
| 入口限流 | gateway | 每 actor 每分钟请求数、SSE 连接数 |
| 能力配额 | capability 框架 | 按 `cost` 档扣减;LLM token 日配额 |
| agent 自律 | policy 引擎 | 每任务工具调用上限、**ReAct 轮数与 tool 轮数**(§9.19)、subagent 并发上限、安静时段 |
| 服务背压 | 各服务队列 | 队列深度上限,超限返回"稍后再试"而非堆积 |

### 7.6 审计

- 一切变更类 capability 调用落审计:`actor / capability / 输入摘要 / 结果 / ts / trace_id`;
- agent 每次决策落 episodic 记忆:触发 → 观察 → 判定 → 调用 → 结果;
- 活动页(§10.8)是审计的可视化;agent 的可逆行动必须给出撤销入口。

### 7.7 配置与密钥

- 配置分级:默认 < 配置文件 < 环境变量;每个服务只读自己前缀的配置;
- 密钥由 platform/secrets 统一保管:加密落盘、按需分发、日志与事件 payload
  框架层脱敏;**secret 设置项的唯一写入口是用户本人经 secrets 写入**(§8.8);
- BYOK:用户填自己的 LLM key;无 key 时 agent 降级(§9.18)。

### 7.8 可观测性

- 结构化日志,`trace_id` 贯穿一次交互的所有进程;
- 每次 LLM/tool call 记录模型、token、耗时、成本(→ 用量页 §10.9);
- agent trajectory 持久化,可回放任意一次任务。

### 7.9 settings(设置项框架)

- 每个设置项的定义:`key / schema / 默认值 / 所属模块 / secret 标记 / 变更事件名`;
- 各服务在自己的 `settings.py` 里声明本服务的设置项;框架负责存取、校验、
  发 `settings.changed` 事件、按 actor 区分写权限(secret 项拒绝 agent);
- 设置页不硬编码任何设置项——向 gateway 要"全部设置 schema"动态渲染(§10.11)。

### 7.10 健康探测与统一错误码(服务故障的隔离与体面)

**目标:一个服务出问题,其他全部不受影响;出问题的那一个,报错要清楚、可行动。**

- **健康探测**:每个服务暴露 `health` 端点;gateway 周期探测 + 请求时被动感知;
  健康变化发 `service.health.changed` 事件(前端服务徽章、agent 都能感知);
  desktop/启动器兼任进程监督者:服务崩溃自动拉起,连续拉起失败标记不可用。
- **统一错误码**:契约包定义,形态 `<域>.<码>`,HTTP 状态映射——
  例:`GRAPH.UNAVAILABLE`(503)、`GRAPH.QUEUE_FULL`(429)、
  `SOURCES.REPO_NOT_FOUND`(404)、`LLM.AUTH_REQUIRED`(401)。
  错误体统一为 `{ error: { code, message, service, hint, trace_id } }`。
- **前端降级态**:每个页面模块必须实现"服务不可用"态——友好提示 + 错误码 +
  [重试] + [告诉 Lucien](一键把错误上下文带进对话)。示例:图谱服务挂了,
  打开图谱页显示"图谱服务不可用(GRAPH.UNAVAILABLE · 503)",
  其余页面照常工作。
- **agent 侧**:capability 调用失败返回同样的结构化错误;agent 按错误码决策——
  `UNAVAILABLE` 重试/等待,`QUEUE_FULL` 稍后,连续失败则向用户报告而不是死循环。
- **事件流自身故障**(platform 级):各进程本地缓冲事件,恢复后补发;
  这是唯一"全局性"设施,因此实现必须最保守。

## 8. 领域服务(services)

**本章列出的能力均为初始最小集,不封闭。** 各领域能力的完整设计(包括图谱的全部工具、
office 的全部操作、code-exec 的全部运行时等)在对应模块卡 `docs/modules/<domain>.md`
中详细设计并持续演进;新增能力只改该服务的 `capabilities.py` 注册表与模块卡,本文档不动。

### 8.1 通用模板(六件套)

```
services/<domain>/
├── capabilities.py    # 能力注册表(单一事实来源)
├── rest.py            # 注册表 → FastAPI router
├── mcp_server.py      # 注册表 → FastMCP server(stdio / streamable HTTP)
├── worker.py          # 本领域队列与调度(无长任务则省略)
├── store.py           # 本领域数据访问(独立命名空间)
├── settings.py        # 本服务设置项声明(经 platform/settings 框架)
├── service.json       # 模块卡:名称、端口、能力清单、订阅的事件类型
└── tests/             # 本服务全部测试
```

### 8.2 sources(资源聚合服务)

统一管理"可学习的资源"。**聚合服务内部同样脱耦**:每种资源类型是
`modules/` 下的自包含子模块(自己的 capabilities/store/worker),
聚合层只做注册表合并与类型分发,子模块之间互不 import。

- 初始子模块:
  - `repo`:GitHub 仓库。能力:`import_repo / list_repos / sort_repos /
    get_readme / remove_repo`;长任务:clone 到 `workspace/repo/`(job + 进度事件);
  - `books`:书籍。能力:`add_book / get_chapter / list_books / remove_book`;
  - `news`:新闻。能力:`fetch_news / list_news / remove_news`。
- 新增类型(如"论文")= `modules/` 下新增自包含目录,聚合层零改动。
- 发布事件:`source.added / source.removed / source.ready`(解析完成,
  由 agent 决定是否建图谱索引——书籍/新闻走 AI 管线,§8.4)。

### 8.3 notes(笔记服务)

- **格式仅 Markdown**(决策 §15;富文本是未来可能的子类型);
- 能力:`create_note / update_note / delete_note(L2)/ list_notes /
  get_note / link_note`;
- 事件:`note.created / note.edited`;笔记可关联资源与图谱节点;
- `list_notes` 默认只返回元数据摘要(标题/标签/更新时间),正文按需 `get_note`——
  服务侧就支持按需加载(§9.20)。

### 8.4 graph(图谱服务)

**两条建图管线,互不 import**:

| 管线 | 用途 | 方式 |
|---|---|---|
| `pipelines/code`(程序化) | **源码分析、仓库关联度分析**(当前引擎的能力范围) | 引擎自动解析,无需 LLM |
| `pipelines/ai`(AI 建图) | 书籍、新闻、文档等文本内容 | **agent 阅读内容后经 `set_node` / `set_relationship`(upsert 语义)直接建图** |

**引擎(engines/,程序化管线的执行者)**:**默认 C 引擎**(sidecar 子进程),
**不可用时自动回退 Python 引擎**并发出事件告知;适配层对管线屏蔽差异;
用户可在设置里强制指定(决策 §15)。

- 初始能力原语:`enqueue_index / cancel_index / reorder_queue /
  set_node / set_relationship / query_graph / get_subgraph`;
  其中 `set_node` / `set_relationship` 只是基础写入原语——完整工具集(子图提取、
  路径查询、邻居展开、批量操作、节点合并、图统计等)在 `docs/modules/graph.md`
  中详细设计并按需扩充,本文档不枚举;
- 自带优先级队列:enqueue/cancel/reorder,并发上限、重试、backoff;
  进度事件 `task.progress`;待命语义:队列空则空转,有任务即醒;
- AI 管线与程序化管线产出**同一份图存储**——用户手动建的节点、
  引擎解析的节点、agent 建的节点在同一个图谱里,来源字段区分(actor + pipeline)。

### 8.5 code-exec(代码执行服务)

- 能力:`run_file / run_snippet / list_runtimes`;长任务走 job + 进度事件;
- **容器沙箱为最终形态**(决策 §15):每次执行起一次性容器,挂载
  `workspace/sandbox/`,默认无网络、资源限额(CPU/内存/时长);
  保留"真实环境"模式(用户显式指定路径,L2 确认);
- 首批语言环境:Python / Node / Shell;语言环境是数据,可扩展。

### 8.6 office(办公聚合服务)

Word 类与 PPT 类是**两个子领域**,office 是聚合服务(与 sources 同模式,§6.4):
`modules/doc`(Word 类)与 `modules/slides`(PPT 类)各自自包含,
互不 import;未来 sheets 等类型 = 新增子模块。

- `doc` 能力:`create_doc / insert_block / update_block / restyle /
  export_doc / get_selection_context`;
- `slides` 能力:`create_deck / add_slide / update_slide / layout /
  export_deck / get_selection_context`;
- 文档模型结构化(段落/标题/图片/版式),导入导出 .docx/.pptx;
  产物落 `workspace/exports/`;
- "鼠标指哪 agent 知道":编辑器上报选区/焦点(节流),agent 经
  `get_selection_context` 拿结构化上下文,修改经同一 capability 落回;
- 事件:`doc.edited / doc.selection.changed`。

### 8.7 browser(浏览器自动化服务)

- 能力:`open_url / click / fill / read_page / screenshot`;
- web 端受同源限制只读抓取;完整自动化由 desktop 的 browser-host(Electron)
  执行,本服务下发指令、回收结果;一切出网请求经网络权限层(§9.9)。

### 8.8 llm 与 settings(LLM 提供商 + 应用设置)

**llm 服务**:

- 领域:LLM 提供商目录与连接管理。内置常见提供商数据(名称、base_url、
  API 格式(chat / anthropic messages)、模型清单);支持自定义提供商;
  agent 可联网搜索补充未知提供商的信息(经网络权限);
- 能力:`list_providers / get_provider_defaults / add_provider /
  update_provider / test_connection / list_models`;
- **secret 边界**:provider 元数据(agent 可写)与 api key(只有用户可写)
  是两类数据——key 走 platform/secrets,`add_provider` 不接受 key 字段;
  这就是"帮我添加一个 LLM"场景里 agent 能填好一切、唯独 key 留给用户的机制
  (场景 G)。

**settings 服务**:

- 领域:应用级设置聚合——外观(主题等)、仲裁模式、安静时段、触达预算、
  隐私开关……主题能力 `set_theme / get_theme / list_themes` 在此
  (cost:low,可静默执行,`settings.changed` 事件让 web 热切换);
- **每个服务都自带设置**:notes 的默认排序、graph 的并发上限与引擎选择、
  code-exec 的资源限额、agent 的轮数上限(§9.19)……都在各自的
  `settings.py` 声明;
- 设置页经 gateway 拿到所有服务(含 agent 自身)的设置 schema 动态渲染;
  用户与 agent 走同一组 `get_settings / set_setting` capability,
  **secret 项对 agent 写入拒绝**(铁律 7 的隐私例外)。

### 8.9 未来新领域

复制 `_template` → 写 capabilities 与 settings → 在 gateway 注册 → 完成。
agent 端经 `list_tools` 动态发现,设置页经 schema 聚合自动出现新分组,
**两处都零改动**。

---

## 9. Agent Runtime 详设

### 9.1 Runtime 的十二项职责

Runtime = 让 agent 真正"跑起来"的执行环境与控制层(Agent 是程序逻辑,Runtime 是
操作系统 + 调度器,Tools 是外部能力,LLM 是决策引擎)。Voyager 的 runtime 承担:

| # | 职责 | 落点 | 要点 |
|---|---|---|---|
| 1 | 执行引擎 | runtime/loop.py | LLM 推理 → tool call → 执行 → 再推理 的循环 |
| 2 | 调度 | runtime/scheduler.py | subagent 生命周期、并发、优先级、一次性定时器 |
| 3 | 状态管理 | runtime/state.py | run/step/plan/tool_results/checkpoint,断点续跑 |
| 4 | 上下文管理 | context/ | 装配、压缩、**按需加载**(§9.12、§9.20) |
| 5 | 工具运行时 | tools/ + clients/ | 发现(list_tools)、参数校验、权限、超时、序列化 |
| 6 | 记忆协调 | memory/ | 四种记忆的读写调度(§9.11) |
| 7 | 事件系统 | runtime/events.py | runtime 级事件 + 领域事件订阅 |
| 8 | 持久化 | runtime/state.py | checkpoint / event log / trajectory |
| 9 | 并发与多 agent | master/ + subagent/ | 派生、通信、汇总、资源限制(§9.4) |
| 10 | 容错恢复 | runtime/recovery.py | retry/backoff/熔断/checkpoint/rollback(§9.17) |
| 11 | 安全沙箱 | policy/ + tools/ | 权限引擎、fs jail、网络层(§9.9、§9.10) |
| 12 | 可观测 | runtime/observability.py | 每次 LLM/tool call 的 token、耗时、成本(§7.8) |

### 9.2 总体结构:Master + Observe + Subagent 集群

```
                       事件流(user.message / user.online / user.activity / task.* / …)
                                    │
                          ┌─────────▼─────────┐
                          │  runtime/loop.py  │  取事件,分类
                          └─────────┬─────────┘
              ┌─────────────────────┼────────────────────────┐
              ▼                     ▼                        ▼
      用户消息/任务事件       行为观察类事件              定时/系统事件
              │                     │                        │
      ┌───────▼────────┐   ┌────────▼────────┐      ┌────────▼────────┐
      │ Master(Lucien) │   │  observe 模式   │      │ proactive 引擎  │
      │ 统筹·仲裁·派单  │   │ 只读探查+wait/act│      │ 问候/追问(§9.8) │
      └───────┬────────┘   └────────┬────────┘      └────────┬────────┘
              │ spawn               │ act(经 policy 分级)     │ spawn(一次性)
     ┌────────▼─────────────────────▼─────────────────────────▼────────┐
     │                    subagent 集群                                │
     │        对话型(用户可交流)│ 执行型(静默)                        │
     └─────────────────────────────────────────────────────────────────┘
```

- **Master(Lucien)是唯一常驻的 agent**。它不直接干具体活:分解任务、派出
  subagent、仲裁新消息、维护全局摘要、监督与汇总。
- **对话型 subagent**:chat 页与悬浮窗里和用户说话的"前台"(带人格),
  接受输入并把意图摘要上报 master。
- **执行型 subagent**:用户不可见的"后台",跑具体任务(导入、索引、整理)。
- **observe 模式**:master 的轻量观察态,只用只读 capability + `wait`/`act`
  两个控制动作。
- **直聊模式(设置项,默认关闭,决策 §15)**:开启后简单问答由 Lucien 直接回复,
  不派对话 subagent、不启动任务管线;关闭时(默认)一切用户消息经仲裁,
  由对话 subagent 承接——这让"执行任务中来新消息"成为常规情形而非异常分支。

### 9.3 人格团队(已定稿)

**常驻 1 个 + 人格预设 4 个 + 用户自建**。"角色"不是常驻进程,而是纯数据
(名字/气质/能力面模板/默认模式),master 按需以某人格派出 subagent,干完即收。

| 人格 | 气质来源 | 职责定位 |
|---|---|---|
| **Lucien** | lux(光):照亮全局 | 唯一常驻 master:统筹、仲裁、直聊(开关) |
| **Iris** | 信使女神 | 侦察检索:调研、找资料、项目导览 |
| **Elio** | 太阳 | 讲解导师:串讲、答疑、出题 |
| **Miyai** | 精致仪式感 | 策展整理:归类、笔记、文档生成 |
| **Atlas** | 背负天球者 | 图谱向导:图谱漫游讲解 |

chat 页/悬浮窗前台人格默认由 Lucien 按场景指派,用户可在设置里指定固定人格;
人格风格(毒舌/热心/严谨…,§9.14)与人格正交可叠加。

### 9.4 Subagent 体系

#### 9.4.1 派出(spawn)四件套

1. **任务书**:目标、约束、完成判定、汇报节奏、轮数上限(§9.19);
2. **能力面(工具白名单)**:权限的实现方式(铁律 6)。能力面 =
   master 工具面 ∩ 人格模板 ∩ 任务需要,**只能收窄不能放宽**;
3. **模式**(§9.4.2);
4. **人格**(对话型必带,执行型通常不带)。

#### 9.4.2 模式授予

| 模式 | 适用 | 说明 |
|---|---|---|
| **ReAct** | 多数任务;**Lucien 强制使用**(决策 §15) | 推理-行动循环 |
| Plan-Execute | 多步骤、步骤间强依赖 | 先出计划,master 可审批再执行 |
| CoT | 纯推理、无工具 | 解题、分析 |
| ToT | 分支探索 | 树状:分岔出多条思路、评估、剪枝,选最优 |
| **GoT** | 多源聚合 | 图状(ToT 做不到的事):允许多个中间想法**聚合**成一个、精炼、循环——如"把三份搜索结果合成一份报告"、多份资料共同建图 |
| Reflexion | 易失败、值得重试的任务 | 失败后自我反思并重规划,重试受轮数上限约束 |
| Direct | 单次直答 | 无循环无工具,最快最省 |

ToT 与 GoT 的区别在于中间结果能不能**合并**:树只能选一条路走下去,
图可以把几条路的产物汇成一个新节点继续——所以多源合成类任务用 GoT。
模式是 runtime 的执行策略(决定状态机形状与 checkpoint 粒度),不是提示词技巧;
由 master 按任务性质选定,用户自建 subagent 时可显式指定(§9.4.4)。

#### 9.4.3 生命周期

`spawned → running → (paused/resumed) → completed | failed | cancelled`。
每次迁移发 runtime 事件;master 可暂停、接管、终止;运行中实例的实时状态
卡片展示在 Agent 团队页(§10.10)。

#### 9.4.4 用户自建 subagent

Agent 团队页"造人":名字、人格描述、**能力面(勾选工具)、默认模式
(§9.4.2 全部七种)、权限档位、轮数上限**、触发方式(master 自动派遣 /
仅手动)。注册进 `subagent/registry.py`,对 master 而言与人格预设同构。

#### 9.4.5 subagent 不是微服务

subagent 是 agent 进程内的**决策实例**(asyncio task 级,轻、随任务生灭);
领域服务是**功能进程**(重、常驻)。前者调后者的 capability。

### 9.5 对话与任务双轨道

agent 的输出与执行是两条并行轨道,通过事件汇合:对话轨道流式生成,
任务轨道跟踪 job_id。任务完成事件到达时,由对话人格在**自然停顿处**插话
("项目刚才已经导入好了,现在开始建索引"),而不是生硬打断。
两条轨道共享同一个 subagent 实例上下文,但分属不同的输出通道。

### 9.6 分层上下文模型

不共享全文,按层持有(正面解决"双份上下文烧 token"的问题):

| 层 | 持有者 | 内容 |
|---|---|---|
| 全局层 | master | 用户画像摘要、全局规则、各 subagent 的**状态摘要卡片**(在做什么/进度/最近汇报)、任务清单 |
| 任务层 | 各 subagent | 自己任务的完整上下文(消息、工具结果、中间产物) |
| 按需层 | subagent → master | subagent 用 `request_context(query)` 工具向 master 申请画像/相关摘要 |
| 监督层 | master → subagent | master 有权读取任一 subagent 全部上下文(仲裁/审计/接管) |

摘要卡片由 `master/digest.py` 维护:subagent 按汇报节奏上报,master 只留
有损压缩后的卡片。**token 账**:master 每轮只看全局层(通常几百 token);
仲裁同理(§9.7)。上下文的权威存储是 runtime/state.py,内存里只是视图。
更广义的"索引常驻、全文按需"加载体系见 §9.20。

### 9.7 消息仲裁:任务执行中来了新消息

三模式,设置里选默认(**默认:排队**,决策 §15),对话里可随时切换:

| 模式 | 行为 |
|---|---|
| **排队**(默认) | 新消息进队列,当前任务完成后按序处理 |
| **自动** | 仲裁器直接判定去向(见下) |
| **引导** | 对话 subagent 先接住(澄清、记录),不打断执行,用户显式决定何时切入 |

**仲裁器(arbiter)是轻量判定,不是第二个大模型上下文**:输入只有
新消息文本 + 当前任务摘要卡片(几十 token)+ 规则;输出三选一——
**注入**(相关且重要 → 作为中断事件注入执行中 subagent)、
**排队**(无关/不紧急)、**急停**(停止/取消类 → 立即中断)。
一次小模型调用约几十~几百 token。拿不准时降级为"问一句用户",宁可问不可错注。

### 9.8 主动触达(proactive):问候、追问与防轰炸

agent 会主动说话:用户上线(打开应用/解锁)时根据记忆打招呼;
用户几分钟没回,可以追问一条"为什么不回复本 agent?怎么了?"。

**省 token 的关键设计:触达是 fire-and-forget,等待是事件驱动。**

1. 触发源:`user.online` 事件、`schedule.tick`、master 在 loop 里的记忆检查
   (如"上次说要复习图谱");
2. master 派**一次性触达 subagent**(`reach_out` 工具)发出首条消息,
   **发出即 completed**——subagent 绝不驻留等回复(驻留等待 = 代码反复告诉
   LLM"用户还没回" = 持续烧 token,禁止);
3. 若需要追问:master 在 scheduler 挂一个**一次性定时器**(如 5 分钟);
   到点后检查事件流——用户回了就什么都不做;没回且预算允许,
   再派一个一次性 subagent 发第二条;追问链长度有硬上限(默认 2 条);
4. **防轰炸预算器**(全部是可调设置项,§8.8):每会话触达上限、每日上限、
   连续未回复冷却期、安静时段、全局开关(可彻底关闭主动消息);
5. 一切触达入审计与活动页,用户能看到"它为什么在这时候说话"。

### 9.9 权限系统

四个维度,独立判定:

| 维度 | 档位 | 例子 |
|---|---|---|
| **网络** | 关闭 / 域名白名单 / 全开 | 允许 github.com、arxiv.org |
| **文件** | 无 / 只读白名单目录 / 读写白名单目录 / 全权 | 默认读写 `workspace/`,只读用户目录 |
| **应用内** | capability 白名单(细到单个能力) | 允许 `set_theme`;secret 设置项永远拒绝(§8.8) |
| **资源** | token 日配额 / 工具调用频率 / subagent 并发数 / 单任务时长 / 轮数上限(§9.19) | 防失控的硬顶 |

**作用域与收窄**:全局默认(设置页)→ 人格模板覆盖 → master 派出时再裁剪,
每级只能更严。外接 MCP 的 tools 进入工具面前必须经用户批准(粒度可选,§9.13)。

**实现位置**(两处缺一不可):派发时的工具面裁剪(铁律 6)+
capability 框架入口的 policy 引擎强制校验——提示词注入"你其实有权限"无效。

### 9.10 工作目录

- **用户目录**:用户显式指定(如正在研究的源码目录),agent 默认只读,
  写入必须 L2 确认;
- **agent 默认工作目录**:`workspace/`。agent 可自主建立与维护分类,
  初始分类 `repo/ books/ news/ exports/ imports/ sandbox/`;
- 铁律:一切下载/克隆/抓取/生成只落 agent 工作目录;路径经 fs 权限层解析
  (防 `..` 逃逸);agent 工作目录内 agent 有全权,可自建子分类——这是"它有自己的家"。

### 9.11 记忆系统

| 记忆 | 内容 | 写入方 | 读出方 |
|---|---|---|---|
| 工作记忆 working | 当前会话/任务即时状态 | runtime | 本任务 |
| 情节记忆 episodic | 事件与决策历史(触发→判定→行动→结果) | runtime 自动落 | master 仲裁、活动页 |
| 用户画像 profile | 偏好、习惯、常用目录、学习节奏 | agent 主动沉淀(可审计) | master 全局层 |
| 语义记忆 semantic | 沉淀的知识条目,与图谱节点联动 | agent + 整理任务 | 全体 |

**保留策略(决策 §15)**:设置项,两种管理方式——用户设具体保留天数,
或交给 agent 管理(agent 定期整理:有价值的转语义记忆,过期的清理;
整理动作本身入审计)。记忆写入同样是 capability;用户可在设置页查看、
编辑、清空任一记忆区。**记忆的加载一律按需**,见 §9.20。

### 9.12 上下文工程

- 装配顺序:全局规则 → 人格 → 用户画像摘要 → 任务书 → 摘要卡片 → 工作记忆;
- 工具结果截断与压缩、消息剪枝、长任务分段 checkpoint 后重建;
- 重建优先"摘要 + 关键原文指针",不做全文回填;
- 一切压缩有损且可审计(压缩前后映射落 episodic)。

### 9.13 全局规则、Skill、Hook、插件与外接 MCP

- **全局规则**:用户级规则文件,master 全局层常驻;支持目录级规则
  (某项目目录的规则只在该项目任务中生效);
- **Skill**:可复用过程包(何时用、步骤、所需工具)。来源:用户手写、
  插件带入、**agent 自动整理**(master 发现反复执行的流程 → 提议整理成
  skill → L1 提示用户确认 → 入库)。**skill 全文按需加载**(§9.20);
- **Hook**:事件钩子。钩子点:事件流事件、工具调用前/后、任务生命周期、
  会话开始。形式:命令脚本 / 提示词注入 / capability 调用;
- **外接 MCP**:设置页添加(stdio 命令或 URL)→ 列出其 tools →
  用户批准后挂载进工具面,参与 list_tools 动态发现。
  **批准粒度用户可选**(决策 §15):逐项批准(安全)或整包批准(省事),
  批准记录落审计;
- **插件** = skill + hook + MCP 配置 + UI 面板声明的打包,
  安装时展示完整权限请求清单。

### 9.14 人格与风格

人格 = 名字 + 气质描述 + 能力面模板 + 默认模式(纯数据);
风格预设(毒舌/热心/严谨/简洁…)与人格正交可叠加;
用户可自定义新人格,也可改 Lucien 的显示名——名字只是显示层,
功能由能力面决定。

### 9.15 询问用户(AskUser)

`ask_user` 是 agent 的一等工具。问题类型:`text / single_choice /
multi_choice / slider / rating / confirm / quiz(出题:题干+选项+判分)`。
契约:agent 发请求 → 事件流 → web 渲染弹窗或 chat 内卡片 → 用户作答 →
应答事件回投 → agent 继续。每题带超时与默认答案;全部问答入事件流。

### 9.16 浏览器自动化

见 §8.7。对 agent 而言只是一组 capability,不感知实现差异。

### 9.17 容错与恢复

- 工具调用:超时 + 指数 backoff + 熔断(连续失败暂停并上报);
- 任务级:每步 checkpoint,崩溃重启后 resume 或标记 failed;
- 可逆操作提供 rollback(活动页撤销入口);
- 服务不可用:按统一错误码决策(§7.10),不空转;
- LLM 故障:切换备用 provider / 降级规则模式(§9.18),任务挂起而非丢失。

### 9.18 降级模式(无 LLM key)

对话与派生关闭;observe 退化为确定性启发式(如"导入了项目 → 提示是否建索引");
图谱与队列照常。系统核心功能(导入/索引/图谱/笔记)不依赖 LLM 可用。

### 9.19 轮数上限与资源上限

- **ReAct 轮数**(推理-行动循环次数)与 **tool 轮数**(工具调用次数)
  是两个独立设置项(决策 §15):全局默认 + 每任务覆盖 + 每 subagent 覆盖
  (自建时可设);**用户能改,agent 也能改**(非 secret 设置项,
  agent 修改入审计;调高自己的预算建议 L1 提示用户);
- 超限 → subagent 立即收尾,汇报部分结果与"为什么停",
  由 master 决定继续/放弃/询问用户;
- 配套上限:单任务时长、subagent 并发数、工具调用频率(§9.9 资源维);
- 所有上限命中都发 runtime 事件并入审计——**失控必须可见,而不是静默发生**。

### 9.20 按需加载体系(索引常驻,全文按需)

token 与内存都是稀缺资源。一切"可能很大"的上下文都遵循同一原则:
**索引/摘要常驻,全文按需,检索式注入,加载动作入审计与用量。**
由 `context/loader.py` 统一实现,四类对象:

| 对象 | 常驻(索引层) | 按需(全文层) |
|---|---|---|
| **页面上下文**(悬浮窗/chat 感知用户在干什么) | 页面 provider 的**摘要**:页面类型、条目数量、可见项标题、当前选中/指针目标 | 具体条目内容经 capability 按需取(如 `get_note(id)`);服务侧 list 类能力默认只回摘要(§8.3) |
| **Skill** | skill 索引:名称 + 一句描述(全部常驻,通常几百 token) | 选中某个 skill 才经 `load_skill` 读全文;skill 数量大到索引本身超限,则索引也改检索式 |
| **记忆** | episodic 只带最近 N 条压缩卡片 | 更早的经 `recall_memory(query)` 检索式取回 |
| **用户画像** | 画像摘要(偏好要点,几百 token)常驻 master 全局层 | 画像细节(历史依据)按需经 `recall_memory` |

页面侧的配套约定(前端,§10.12):每个页面模块注册 **provider**,
悬浮窗与 agent 拿到的默认只是摘要——用户在笔记页,agent 知道"36 条笔记,
当前打开《langgraph 笔记》,指针指着第三段",而不是把 36 条笔记全文塞进上下文;
要看内容,再调 `get_note`。图谱页同理:"512 节点 / 1204 边,当前选中节点 X"。

---

## 10. 前端信息架构

### 10.1 导航三组与页面即模块

导航分三组,组间视觉隔离:

| 组 | 页面 | 定位 |
|---|---|---|
| **Agent 域** | Agent Chat(**默认首页**) | 与 agent 的一切交互的主场 |
| **领域域** | 资源库 / 笔记 / 图谱 / 工坊 | 一个(聚合)服务对应一页 |
| **系统域** | 总览 / 活动 / 用量 / Agent 团队 / 设置 | 系统本身的仪表盘 |

- **Agent Chat 是默认页面与第一导航**:打开应用就落在 chat;agent 有权
  跳转页面——`agent.navigate` 事件经事件流到达 shell 的路由即跳转
  ("要看看图谱吗?"→ 用户答应 → 跳转并进入讲解);跳转后对话不中断,
  由常驻悬浮窗接续(§10.12)。chat 里对话的同时,后台任务照常推进,
  进度以卡片形式浮在对话里。
- **页面即模块**(铁律 1 的前端落实):每个页面目录自包含
  (index/components/hooks/store/provider),页面之间不共享组件与状态;
  全应用唯一的共享层是 `bridge/`、`contracts/`、基础 UI 包。
- **一个服务一页**:领域域的页面对应 services 里的(聚合)服务;
  新领域上线 = 新服务 + 新页面,互不触碰。

### 10.2 Agent Chat(默认首页)

- 展示:消息流(带人格头像)、任务卡片(实时进度)、确认卡片、AskUser 弹窗、
  当前仲裁模式指示(默认"排队")、运行中 subagent 徽章、主动触达消息
  (带"为什么找我"的出处)、**产物快速预览卡片**。
- **快速预览**(决策 §15):agent 完成任务产出的 PPT / Word / 笔记(md)等,
  以卡片形式内联在对话里,点击即就地展开预览——不用跳页;预览卡片带
  [在工坊打开] [导出] [撤销] 操作。
- 能做:对话;插话(体验仲裁);切换仲裁模式;一键急停;点开任务卡片看
  trajectory;被引导跳转到任何页面。

### 10.3 资源库 Sources(仓库/书籍/新闻合并页)

- 展示:统一资源流 + 类型筛选(仓库/书籍/新闻/未来类型自动出现);
  每项带索引进度、学习进度;排序(按名/时间/进度)。
- 能做:导入(GitHub URL / 文件 / 订阅源);打开详情(README、章节、笔记、
  图谱入口);删除(L2);甩给 chat("给我讲讲这个");阅读器内选中共上下文。

### 10.4 笔记 Notes

- 展示:笔记列表(md)、标签、关联的资源与图谱节点。
- 能做:增删改;关联图谱节点;让 agent 把对话/资料沉淀成笔记。

### 10.5 图谱 Graph

- 展示:知识图谱(3D)、按资源筛选、节点详情(含来源:手动/引擎/AI)、
  **索引队列面板**(排队/索引中/完成,带优先级)、引擎指示(C / Python 回退中)。
- 能做:手动建节点/连线(与 agent 同 capability);拖动重排、取消任务;
  "讲给我听"进入 Atlas 漫游讲解;强制切换引擎(设置项)。
- **降级态**:graph 服务不可用时显示"图谱服务不可用(GRAPH.UNAVAILABLE · 503),
  [重试] [告诉 Lucien]"——其余页面不受影响(§7.10)。

### 10.6 工坊 Studio

- 展示:文档编辑器(Word 类)、演示编辑器(PPT 类)、代码运行器
  (选语言、选路径/贴片段、容器内执行、看输出)。
- 能做:就地编辑;选区右键"让 agent 改这里";运行代码并把结果钉进笔记;
  打开/导出 agent 生成的 Word/PPT。

### 10.7 总览 Overview

- 展示:最近资源、进行中任务、待确认卡片、agent 今日动态摘要、学习推荐。
- 能做:跳转任一处;处理待确认项。

### 10.8 活动 Activity

- 展示:全量动态流(人与 agent 的一切行为:谁、何时、做了什么、结果,
  agent 自主行动附"为什么");触达记录;可撤销项带撤销按钮。
- 能做:过滤(只看 agent / 只看某资源);撤销;定位到相关对象。

### 10.9 用量 Usage

- 展示:token/成本按天/任务/人格分布;LLM 与工具调用次数;失败与重试统计;
  按需加载的调用量(§9.20 的每次全文加载也计入)。
- 能做:设日配额;导出。(管"消耗";能力与状态去 Agent 团队页。)

### 10.10 Agent 团队 Agents

- 展示:Lucien(master)卡片;人格预设卡片(Iris/Elio/Miyai/Atlas);
  用户自建 subagent 卡片;运行中实例的实时状态。
  每张卡片:**名字与风格、skills、hooks、工具清单、权限档位、默认模式、
  轮数上限、当前在做什么**。
- 能做:启停人格;**造人**(自建 subagent:工具勾选、模式、权限、轮数);
  查看任一运行中实例的上下文(master 视角);急停任一实例。

### 10.11 设置 Settings

分组:**Agent 权限**(网络档位与域名白名单、文件目录白名单、应用内
capability 白名单、资源配额与**ReAct/tool 轮数上限**)/ LLM(提供商管理;
api key 仅本人可填)/ 工作目录 / 仲裁模式与安静时段 / **主动触达**(开关、
预算、追问链长度)/ 全局规则 / 人格与风格 / 外接 MCP 与插件(含批准粒度:
逐项/整包)/ 记忆(查看、编辑、清空、保留策略:天数或交给 agent)/ 隐私
(行为上报类别开关)/ 外观(主题)/ **各服务设置**(gateway 聚合 schema
动态渲染,新服务上线自动出现新分组)。

### 10.12 全局组件与常驻悬浮窗

全局组件:AskUser 弹窗、任务卡片、确认卡片、动态 feed、agent 在场徽章、
kill switch。

**常驻悬浮对话窗**(决策 §15):

- **形态**:除 chat 页外所有页面常驻,可收起为气泡;从 chat 跳转到其他页面时
  对话不中断,自动收进悬浮窗继续;在悬浮窗里的对话与 chat 页是同一会话。
- **页面感知**:悬浮窗知道用户在**哪一页**、**指针/选区在哪**、
  页面的**摘要信息**(经该页面的 provider,§9.20)——笔记页:"36 条笔记,
  当前打开《langgraph 笔记》,指针在第三段";图谱页:"512 节点 / 1204 边,
  选中节点 X"。**只拿摘要,不加载全量**;要细看某条,agent 再调 capability 取。
- **隐私**:敏感界面(设置的密钥区等)不上报指针与内容;全部感知类别
  可在隐私设置里逐项关闭。

## 11. 示例场景(端到端)

### 场景 A:"我想学 langgraph"(边聊边干活 + 插话仲裁)

```
user.message → Lucien 判定:讲解+导入+索引
→ 派 Elio(对话型)开讲;派执行型 subagent 调 sources.repo.import_repo
  (返回 job_id,不阻塞)→ 完成事件 → Elio 在自然停顿处插话
  "已导入,开始建索引" → graph.enqueue_index(程序化管线,C 引擎)
→ 用户插话"顺便把 zod 也索引了,opencode 先算了"
  → 当前为排队模式:消息进队列,任务完成后处理
  (若切到自动模式:仲裁器判定"相关且重要"→ 注入执行中 subagent)
→ 索引完成 → Elio:"要看看图谱吗?" → 用户:"看" → agent.navigate →
  图谱页,Atlas 漫游讲解,对话收进悬浮窗继续
```

### 场景 B:搬书场景(主动帮忙)

```
用户手动导入 opencode 并读 README → user.activity 事件
→ observe:查画像(最近密集看项目)、查队列(空闲)
→ policy:建索引 cost:low 可逆 → 静默 enqueue_index(低优先级)
→ 活动页留痕:"注意到你在看 opencode,已顺手建好索引 [撤销]"
```

### 场景 C:"把这周 AI 新闻整理成 Word 给我"(AI 建图管线)

```
Lucien 派 Iris(调研,网络白名单内抓取)→ 落 workspace/news/
→ 派 Miyai:office.doc.create_doc 生成文档 → workspace/exports/
→ chat 里出现快速预览卡片(就地预览,[在工坊打开] [导出])
→ 同时 Miyai 阅读全文,经 graph.set_node / set_relationship 把关键实体
  与概念建进图谱(AI 管线)→ 完成后:"整理好了,图谱也更新了,要看看吗?"
```

### 场景 D:出题陪读

```
用户:"考考我这章" → Elio → ask_user(type:quiz, 题干+选项)
→ 作答事件 → 判分讲解 → 错题沉淀语义记忆并关联图谱节点
```

### 场景 E:用户自建 subagent

```
Agent 团队页造人:"论文猎手",人格=严谨,工具=web.search+sources.news 写入,
模式=GoT(多源聚合),ReAct 轮数=20 → 注册成功
→ 用户:"以后每周帮我找图神经网络新论文" → 计划任务,每周派出,
  结果进资源库
```

### 场景 F:工坊协同改 PPT

```
用户选中一页 PPT → doc.selection.changed 事件
用户在悬浮窗说:"这页太满了" → 悬浮窗带页面摘要+选区上下文
→ Lucien 派 Miyai → office.slides.update_slide(精简+改版式)
→ 编辑器实时刷新;不满意 → 活动页一键撤销
```

### 场景 G:"帮我添加一个 LLM"(设置 parity 与隐私例外)

```
用户:"帮我添加一个 llm"
→ 对话人格(经 ask_user):"提供商是?倾向哪种 API 格式——
   chat 还是 anthropic messages?"
→ 用户:"kimi 的 plan" → Lucien 查 llm 内置提供商目录;查不到就让 Iris
   联网搜 base_url 与模型清单(网络白名单内)
→ 调 llm.add_provider 填好:名称、base_url、API 格式、模型列表
→ 回复:"都配好了,只差 api key——这是您的隐私,请到 设置 → LLM 手动填入"
   (key 是 secret 设置项,agent 的 set_setting 会被权限层拒绝)
```

### 场景 H:上线问候与追问(主动触达)

```
用户早晨打开应用 → user.online 事件
→ Lucien 查记忆("昨天图谱索引到一半")→ 派一次性触达 subagent:
   "早。langgraph 的图谱昨晚建好了,要接着看吗?" ——发出即完成
→ Lucien 挂 5 分钟一次性定时器 → 到点检查:用户没回 → 预算允许 →
   再派一次性 subagent:"怎么不理本 agent?在忙吗?"
→ 用户仍没回 → 追问链达上限(2 条),进入冷却;全程活动页可见
```

### 场景 I:图谱服务挂了(故障隔离与体面报错)

```
C 引擎 sidecar 崩溃 → graph 自动回退 Python 引擎,发事件告知(可继续工作)
若整个 graph 进程崩溃 → gateway 探活失败 → service.health.changed 事件
→ 用户打开图谱页:显示"图谱服务不可用(GRAPH.UNAVAILABLE · 503)
   [重试] [告诉 Lucien]";其余页面照常
→ agent 侧调用 graph 收到同样结构化错误:重试 → 仍失败 →
   向用户报告"图谱服务起不来,错误码 …,日志在 …,要我换个方式吗?"
→ 进程监督者自动尝试拉起;恢复后发健康事件,页面自动恢复正常
```

## 12. 依赖矩阵

允许方向(单向,自上而下):

```
apps      ──允许──▶ contracts(类型)+ 基础 UI 包
gateway   ──允许──▶ contracts + capability + actor + limit + audit + settings + health
services  ──允许──▶ platform/*(机制库,在 service.json 声明)
agent     ──允许──▶ contracts + capability + eventbus + policy 所需机制
plugins   ──允许──▶ 仅声明式描述,不 import 任何实现
聚合服务内部:壳 ──允许──▶ 子模块注册表(只读合并);子模块之间 ──禁止── 互相 import
graph 内部:pipelines ──允许──▶ engines/adapter(只经适配层);两条管线之间 ──禁止── 互相 import
```

**禁止**:

- 任何模块 import 另一模块的实现代码(只允许 contracts 类型与 platform 机制);
- 服务读其他服务的数据表;服务 import agent 或 apps;
- platform import 任何业务模块,或出现领域词汇、品牌名;
- agent 直接写业务库表;
- 前端页面之间共享组件/状态(共享只能经 bridge/contracts/基础 UI)。

CI 依赖扫描强制执行,违反即构建失败。

## 13. 工程规约

### 13.1 独立开发、编译与运行

- 每个领域服务:进入目录即可独立起进程(自带注册表 → REST + MCP),
  测试只跑自己目录;
- agent:独立进程,启动时按 service.json 发现并连接各服务;
- gateway / web:各自独立,web 只需 gateway 一个地址;
- 单体模式(§3.3):一个命令装进单进程供调试;
- **验收标准**:新增领域 = 复制 `_template`,不触碰任何其他目录。

### 13.2 文件级脱耦规约

- 一个文件一个职责:handler 文件不写路由装配,装配文件不写业务;
- 按业务内聚组织目录,不按类型堆叠;禁止万金油 `utils.py` / `misc/`;
- 文件行数软上限(建议 ≤300 行),超限优先拆分;
- 评审问题:"这个文件删掉,影响半径是多大?"——答不上来就是耦合信号。

### 13.3 命名中性规约

- 目录、文件、变量、函数、包名、配置键:一律按**功能/职责/边界**命名
  (如 `eventbus`、`arbiter`、`workspace`),不出现品牌名;
- 品牌字符串集中在品牌配置文件;用户可见文案经 i18n/品牌层注入;
- 改品牌 = 改一处配置;代码全局搜索品牌名应为零结果(CI 检查)。

## 14. 演进路线(面向最终形态的建设顺序)

1. **地基**:platform(contracts/capability/eventbus/actor/settings/health)
   + gateway + sources(repo 子模块)与 graph(程序化管线)两个服务 +
   agent 最小 loop(对话 + 异步任务);
2. **agent 成人**:Lucien + subagent 体系 + 分层上下文 + 仲裁(排队默认) +
   policy 权限 + 工作目录 + 轮数上限;
3. **主动性**:observe + 行为上报 + 记忆 + skill 自动整理 + 主动触达 +
   悬浮窗与页面感知;
4. **场景扩张**:sources 加 books/news + graph 的 AI 管线 → office(doc/slides)
   → code-exec(容器) → browser(desktop) + llm 服务;
5. **生态**:插件与外接 MCP、自建 subagent、可选多机部署(微服务化平移)。

## 15. 决策记录(已定稿)

| # | 议题 | 决策 |
|---|---|---|
| 1 | 角色团队 | 仅 Lucien 常驻;Iris/Elio/Miyai/Atlas 为人格预设;navigator 并入 Iris,scribe 并入 Miyai;用户可自建 |
| 2 | 直聊模式 | 保留开关:开启时简单问答由 Lucien 直接回复;**默认关闭** |
| 3 | 仲裁默认模式 | **排队** |
| 4 | 代码执行沙箱 | 最终形态为**容器**;首批语言 Python/Node/Shell |
| 5 | 桌面端 | **Electron** |
| 6 | 图谱引擎 | 源码分析**默认 C 引擎,不可用自动回退 Python**(用户可强制);布局引擎同属此适配层;几十万节点级大图依赖 C |
| 7 | 外接 MCP 批准粒度 | 用户可选:逐项 / 整包 |
| 8 | 记忆保留策略 | 设置项:用户设保留天数,或交给 agent 管理 |
| 9 | 品牌与命名 | 暂定 Voyager;**代码(目录/文件/变量/函数/配置键)不出现品牌名**,一律按功能/职责/边界中性命名,CI 检查 |
| 10 | 主动触达 | 支持问候与追问;fire-and-forget subagent + 一次性定时器;追问链上限 2 条;全套预算与开关 |
| 11 | 轮数上限 | ReAct 轮数与 tool 轮数是两个独立设置项(全局/任务/subagent 三级);**用户可改,agent 也可改**(非 secret,入审计) |
| 12 | 设置 parity | 用户能改的 agent 都能改;secret(api key 等)仅用户可写 |
| 13 | 前端 | Agent Chat 为默认首页;导航三组(Agent 域/领域域/系统域);项目库与知识库合并为"资源库",对应 sources 聚合服务(内部子模块脱耦) |
| 14 | 模式池 | ReAct(Lucien 强制)/ Plan-Execute / CoT / ToT / **GoT**(多源聚合)/ Reflexion / Direct |
| 15 | office | 聚合服务:`doc`(Word 类)与 `slides`(PPT 类)两个脱耦子模块;未来类型新增子模块 |
| 16 | 图谱建图 | 双管线:程序化(源码分析 + 仓库关联度)/ AI 管线(agent 经 `set_node`/`set_relationship` 直接建图,书籍新闻文档走这条);同一图存储,来源可区分 |
| 17 | 悬浮窗 | 常驻悬浮对话窗;跨页面导航对话不中断;页面感知经 provider 摘要 + 两级加载(§9.20) |
| 18 | 产物预览 | chat 内产物卡片快速预览(PPT/Word/md 笔记),就地展开,可跳工坊/导出/撤销 |
| 19 | 故障隔离 | 单服务故障不影响其余;统一错误码 + 页面降级态 + 进程监督自动拉起(§7.10) |
| 20 | 笔记格式 | 仅 Markdown;富文本是未来可能的子类型 |
| 21 | 按需加载 | 页面上下文/skill/记忆/画像统一"索引常驻、全文按需、检索式注入、加载入审计"(§9.20) |
