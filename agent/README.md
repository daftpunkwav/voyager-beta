# agent — Agent Runtime

常驻进程,系统的决策者(docs/architecture.md §9)。有自己的事件循环,
**不因用户输入才工作**:观察事件流,自主决定是否行动。

装配入口 `main.py: build_agent()`(测试同用);运行:仓库根 `python -m agent.main`。

| 目录 | 职责 | 文档锚点 |
|---|---|---|
| runtime/ | 运行时底座:事件循环、调度、状态、容错、观测 | §9.1 |
| master/ | 主 agent(统筹/仲裁/摘要/主动触达) | §9.2 |
| personas/ | 人格预设(纯数据:风格/能力面模板/默认模式) | §9.3 |
| subagent/ | 派出、实例状态机、七种模式、用户自建注册 | §9.4 |
| policy/ | 权限引擎(四维)、行动分级 L0/L1/L2 | §9.9 |
| memory/ | 画像/情节/语义/工作 四类记忆 | §9.11 |
| context/ | 装配、压缩、按需加载器 | §9.12/§9.20 |
| skills/ | skill 索引与自动整理 | §9.13 |
| hooks/ | hook 加载与触发 | §9.13 |
| tools/ | agent 自身工具(询问用户/派 subagent/fs/shell/web…) | §9.4 |
| clients/ | 各服务的 MCP client 连接池与服务发现 | §9.4 |

顶层 `capabilities.py` / `settings.py`:agent 自己也暴露能力(读/改 agent 设置、
查记忆、查任务),经 gateway 与用户同权(§2 铁律 4 parity)。

实现顺序见 §14:第 2 步"agent 成人"与第 3 步"主动性"已完成(测试见 tests/)。
