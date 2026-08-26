# 后端全面审计报告

> **审计日期**: 2026-08-25
> **审计范围**: `platform/`(7 子包,20 源文件) · `services/`(12 服务,70+ 源文件) · `agent/`(48 源文件) · `deploy/`(4 文件)
> **审计维度**: 脱耦 · 代码质量 · 注释清晰度 · 现代开发规范 · 安全
> **参考基准**: `architecture.md`(1316 行) · `modules/*.md`(13 张模块卡) · `phases/*.md`(执行手册)
> **审计方法**: 3 个并行深度审计 agent(平台/服务/Agent) + 主审查人交叉验证关键文件

---

## 目录

- §1 总评
- §2 CRITICAL 级发现
- §3 HIGH 级发现
- §4 MEDIUM 级发现
- §5 LOW 级发现
- §6 脱耦矩阵验证
- §7 安全检查验证
- §8 架构亮点
- §9 修复优先级建议

---

## §1 总评

| 维度 | 评级 | 说明 |
|------|------|------|
| **脱耦** | **A+** | 全层级零违规:platform 不上引、服务间互不 import、聚合子模块互不 import、agent 只经 capability 调用 |
| **代码质量** | **A** | frozen dataclass、统一 ServiceError、`from __future__ import annotations`、§X.Y 标注;少量文件超限、少量类型缺失 |
| **注释** | **A+** | 全中文注释、模块级 docstring、架构引用精准、演进说明完备 |
| **现代规范** | **A** | Python 3.11+ 写法、async/await 全链路、uv workspace;少量 CPython 内部 API 使用 |
| **安全** | **A-** | 加密仓、参数化 SQL、审计脱敏、secret 写保护均到位;3 处 SSRF/路径穿越需关注 |

**整体结论**: 这是一个架构执行力极强的项目。八条铁律在代码中得到了忠实落地,尤其是"全层级脱耦"和"一份 Action 模型"两条做得堪称教科书。需要关注的问题集中在 **4 个文件超限** 和 **3 个安全边界案例** 上。

---

## §2 CRITICAL 级发现 (3 项)

### C1. 文件超限: `services/graph/engines/python/indexer.py`

| 属性 | 详情 |
|------|------|
| **文件** | `services/graph/engines/python/indexer.py` |
| **行数** | 1162 行 |
| **超限幅度** | 287% (300 行软限) |
| **违规规则** | architecture.md §13.2: "文件行数软上限(建议 ≤300 行),超限优先拆分" |
| **现状** | 多语言静态索引器(Python/JS/TS/Go/Rust/Java/Markdown 全部在一个文件内),包含语法解析、节点提取、调用关系分析等全部逻辑 |
| **影响** | 单文件不可理解、不可单独测试、不可替换;修改任一语言的索引逻辑需在 1162 行中定位;新语言扩展需改同一文件 |
| **建议** | 拆为 `indexer_core.py`(编排+共享工具) + `indexer_python.py` / `indexer_js.py` / `indexer_go.py` 等按语言分文件 |

### C2. 文件超限: `services/graph/engines/python/engine.py`

| 属性 | 详情 |
|------|------|
| **文件** | `services/graph/engines/python/engine.py` |
| **行数** | 742 行 |
| **超限幅度** | 147% |
| **违规规则** | architecture.md §13.2: 文件行数软限 |
| **现状** | GraphEngine 类包含 `search_graph` / `search_code` / `trace_path` / `query_graph`(Cypher 子集解析器) / `get_architecture` / `export_graph` + 多个辅助函数 + 模块级单例 + zstd 压缩 |
| **影响** | 搜索、查询、路径追踪、导出等独立关注点耦合在单类中;修改 Cypher 解析可能影响搜索;测试只能整体测,无法隔离 |
| **建议** | 拆为 `engine.py`(核心 + index_repository) / `engine_search.py` / `engine_query.py` / `engine_trace.py` |

### C3. SSRF: `services/sources/modules/news/capabilities.py`

| 属性 | 详情 |
|------|------|
| **文件** | `services/sources/modules/news/capabilities.py` |
| **行** | 42-43 |
| **类别** | 安全:SSRF |
| **现状** | `fetch_news` 对用户提供的 `url` 参数直接 `httpx.get(url)`,无域名白名单、无内网 IP 拒绝、无重定向目标校验 |
| **复现** | 调用 `fetch_news(url="http://127.0.0.1:8123/api/project-health")` 可探测内部服务;agent 被 prompt injection 后可利用此能力扫描内网 |
| **影响** | 内网服务探测、内部 API 调用、云元数据访问(169.254.169.254) |
| **建议** | 与 agent 网络策略同级——校验 URL 域名或拒绝 RFC 1918/link-local 地址;10 行修复 |

---

## §3 HIGH 级发现 (9 项)

### H1. SSRF via HTTP 重定向

| 属性 | 详情 |
|------|------|
| **文件** | `agent/tools/web.py` |
| **行** | 18 |
| **类别** | 安全:SSRF |
| **现状** | `httpx.AsyncClient(follow_redirects=True)` 跟随白名单域名的 302 重定向到任意目标。Policy engine(`policy/engine.py:89-97`)只在 `decide()` 时检查初始 URL 的域名,不检查重定向后的最终目标 |
| **复现** | 白名单域名 `github.com` 上某页面返回 302 → `http://169.254.169.254/latest/meta-data/`;httpx 自动跟随,agent 读到云元数据 |
| **影响** | 绕过网络白名单,访问内网服务、云元数据、其他本地进程端口 |
| **建议** | 禁用 `follow_redirects`,手动逐跳跟随并每跳校验域名;或在最终 URL 上再次调用 policy.decide |

### H2. URL 解析可绕过白名单

| 属性 | 详情 |
|------|------|
| **文件** | `agent/policy/engine.py` |
| **行** | 92 |
| **类别** | 安全:策略绕过 |
| **现状** | `host = action.target.split("/")[2]` 提取 host。对含 userinfo 的 URL(`https://evil.com@github.com/path`),`split("/")[2]` 得到 `evil.com@github.com`(整体作为 host),而浏览器实际连接 `evil.com`;对含端口的 URL(`https://github.com:8080`),host 带端口号不匹配白名单 |
| **影响** | 构造特殊 URL 可绕过网络白名单,或导致合法 URL 被误拒 |
| **建议** | 用 `urllib.parse.urlparse(action.target).hostname` 提取 host,去除端口并 lowercase |

### H3. Shell 工具无命令消毒

| 属性 | 详情 |
|------|------|
| **文件** | `agent/tools/shell.py` |
| **行** | 14 |
| **类别** | 安全:命令注入 |
| **现状** | `asyncio.create_subprocess_shell(command)` 直接将 LLM 提供的原始字符串传入系统 shell。虽经 `Toolbelt.call()` → `PolicyEngine._decide_shell()` 要求 L2 用户确认,但无命令黑名单、无参数白名单、无危险命令拦截 |
| **影响** | 若确认流被绕过(代码 bug、未来重构、或无 confirm 回调的子 agent),任意 OS 命令可执行 |
| **建议** | 考虑 `create_subprocess_exec` + 参数拆分;至少加破坏性命令(`rm -rf /`、`format`、`shutdown`)黑名单;文档化威胁模型 |

### H4. 文件超限: `services/graph/store.py`

| 属性 | 详情 |
|------|------|
| **文件** | `services/graph/store.py` |
| **行数** | 362 行 |
| **超限幅度** | 21% |
| **现状** | GraphStore 类包含核心 CRUD + `find_path`(双向 BFS) + `merge_nodes`(边迁移+删除) + `export_subgraph`(JSON/Cypher 导出) + `neighbors`(多轮扩边) + `drop_project` |
| **影响** | 读取(查询/展开/路径)和写入(合并/删除/导出)操作耦合,影响半径不可预测 |
| **建议** | `find_path` / `merge_nodes` / `export_subgraph` / `neighbors` / `drop_project` 移至 `graph/operations.py` |

### H5. 文件超限: `services/graph/engines/python/store.py`

| 属性 | 详情 |
|------|------|
| **文件** | `services/graph/engines/python/store.py` |
| **行数** | 355 行 |
| **超限幅度** | 18% |
| **现状** | 包含图存储访问 + `force_layout_3d`(物理模拟:斥力/引力/速度衰减/边界约束,行 282-355) |
| **影响** | 存储逻辑和物理模拟是两个完全不同的关注点,耦合在同一文件 |
| **建议** | `force_layout_3d` 移至 `engines/python/layout.py` |

### H6. 路径穿越: `sources/modules/books/capabilities.py`

| 属性 | 详情 |
|------|------|
| **文件** | `services/sources/modules/books/capabilities.py` |
| **行** | 54-61 |
| **类别** | 安全:路径穿越 |
| **现状** | `add_book` 将用户提供的 `file_path` 复制到 `workspace/books/{title}{fmt}`。`title` 参数未消毒——title 为 `../../etc/passwd` 时,Path 拼接后 resolve 到 workspace 之外 |
| **复现** | `add_book(title="../../etc/passwd", file_path="/tmp/test.pdf")` → 写到 `workspace/../../etc/passwd` |
| **影响** | 覆盖 workspace 目录外的任意文件 |
| **建议** | 消毒 title: `title = Path(title).name`(去除路径分隔符);或用 `dest.resolve().parents` 检查是否在 `workspace/books/` 内 |

### H7. fire-and-forget task 未持有引用

| 属性 | 详情 |
|------|------|
| **文件** | `services/code_exec/capabilities.py` 行 146,166; `agent/master/master.py` 行 170 |
| **类别** | 代码质量:可靠性 |
| **现状** | `asyncio.create_task(_run())` 未保存返回的 Task 对象。Python GC 在 Task 完成前回收它时,异常被静默丢失(仅 emit RuntimeWarning) |
| **影响** | subagent 执行失败可能完全不可见;代码执行容器的错误输出丢失 |
| **建议** | `self._tasks = set(); task = asyncio.create_task(...); self._tasks.add(task); task.add_done_callback(self._tasks.discard)` |

### H8. Content-Length 无上限

| 属性 | 详情 |
|------|------|
| **文件** | `services/graph/engines/python/server.py` |
| **行** | 80 |
| **类别** | 安全:拒绝服务 |
| **现状** | `int(self.headers.get("Content-Length") or 0)` 无上限检查。Graph C engine 的 Python HTTP server 直接读取 body |
| **影响** | 恶意客户端发送超大 body 可耗尽进程内存 |
| **建议** | `length = min(int(...), 10_000_000)` 或在读取前拒绝超限 |

### H9. repo store INSERT OR REPLACE 静默覆盖

| 属性 | 详情 |
|------|------|
| **文件** | `services/sources/modules/repo/store.py` |
| **行** | 64 |
| **类别** | 代码质量:数据完整性 |
| **现状** | `INSERT OR REPLACE INTO repos` 在 URL UNIQUE 约束冲突时整行替换。用户已设置的 category、tags、progress、note、readme 全部被覆盖为默认值 |
| **影响** | 重新导入 repo 时丢失用户元数据(分类、标签、进度、笔记) |
| **建议** | 改为 `INSERT ... ON CONFLICT(url) DO UPDATE SET name=excluded.name, description=excluded.description, ...`(只更新来源字段,保留用户元数据) |

---

## §4 MEDIUM 级发现 (20 项)

### Platform 层 (7 项)

#### M1. health monitor stop() 未 await task

| 属性 | 详情 |
|------|------|
| **文件** | `platform/health/platform_health/monitor.py` |
| **行** | 82-85 |
| **现状** | `stop()` 调用 `self._task.cancel()` 后立即 `self._task = None`,未 await 被取消的 task。`finally` 块中的清理代码不会在 `stop()` 返回前完成 |
| **影响** | 健康探测停止时资源泄漏;测试中可能残留未完成的 task |
| **建议** | `self._task.cancel(); try: await self._task; except asyncio.CancelledError: pass` |

#### M2. execute() 参数 registry 无类型注解

| 属性 | 详情 |
|------|------|
| **文件** | `platform/capability/platform_capability/guards.py` |
| **行** | 123 |
| **现状** | `async def execute(registry, name, actor, args, ...)` 中 `registry` 是唯一无类型的参数。为避免循环 import 未导入 `Registry` 类型 |
| **影响** | 静态分析无法校验调用方传入的类型;IDE 补全失效 |
| **建议** | 用 `TYPE_CHECKING` 导入: `if TYPE_CHECKING: from platform_capability.registry import Registry` |

#### M3. execute() 函数职责过多

| 属性 | 详情 |
|------|------|
| **文件** | `platform/capability/platform_capability/guards.py` |
| **行** | 122-183 |
| **现状** | 60 行处理 5 个关注点:查找能力 → 鉴权 → 配额 → 入参校验+执行 → 审计。docstring 解释了顺序即语义,但单元测试只能整体测 |
| **影响** | 无法单独测试"鉴权通过但配额不足"等分支;修改审计逻辑需理解全部前置步骤 |
| **建议** | 拆为 `_run_guards()` + `_invoke()` + `_audit()`,保持调用顺序不变 |

#### M4. SQLite store 缺上下文管理器

| 属性 | 详情 |
|------|------|
| **文件** | `platform/eventbus/platform_eventbus/log.py` · `platform/settings/platform_settings/store.py` · `platform/secrets/platform_secrets/store.py` |
| **现状** | 三个 SQLite-backed store 都有 `close()` 方法但无 `__enter__`/`__exit__` 协议 |
| **影响** | 调用方忘记 `close()` 时文件句柄泄漏;异常路径不安全 |
| **建议** | 统一添加 `__enter__`/`__exit__`;或提取 `SQLiteStore` 基类 mixin |

#### M5. Unix 文件权限在 Windows 上无效

| 属性 | 详情 |
|------|------|
| **文件** | `platform/actor/platform_actor/token.py` |
| **行** | 40 |
| **现状** | `os.open(..., 0o600)` 设置 Unix 文件权限。Windows 忽略此模式,文件对所有用户可读 |
| **影响** | 本机令牌文件在 Windows 上权限过宽 |
| **建议** | 文档说明平台限制;或 Windows 上用 `ctypes` 设置 ACL |

#### M6. Fernet key 无最短材料长度检查

| 属性 | 详情 |
|------|------|
| **文件** | `platform/secrets/platform_secrets/store.py` |
| **行** | 31-33 |
| **现状** | `_fernet_for()` 从 SHA-256(材料字符串) 派生 Fernet key。1 字符材料也合法生成有效 key |
| **影响** | 弱密钥材料导致加密强度不足(暴力破解容易) |
| **建议** | 材料长度 < 16 字节时 log warning;或在 `key_material.py` 加最低长度要求 |

#### M7. _repo_env() 路径推断脆弱

| 属性 | 详情 |
|------|------|
| **文件** | `platform/secrets/platform_secrets/key_material.py` |
| **行** | 45-48 |
| **现状** | `Path(__file__).resolve().parents[3]` 假设包以 editable mode 安装且目录深度固定。非 editable install(如 sdist)路径会错 |
| **影响** | 非 editable install 时找不到 `.env` 文件,secrets 功能降级 |
| **建议** | 检查解析路径是否含 `.env`,不含则返回 `None`(已有 fallback,但应文档化此限制) |

### Services 层 (8 项)

#### M8. _ensure() 内函数重复

| 属性 | 详情 |
|------|------|
| **文件** | `services/graph/capabilities.py` |
| **行** | 102-109 vs 197-206 |
| **现状** | `set_relationship()` 和 `set_relationships()` 各自定义了完全相同的 `_ensure(qn)` 内函数(查询或创建占位节点) |
| **影响** | 修改查找逻辑需改两处;DRY 违规 |
| **建议** | 提取为模块级 `_ensure_placeholder_node(store, project, qn, source, actor_id)` |

#### M9. gateway chat 无请求体校验

| 属性 | 详情 |
|------|------|
| **文件** | `services/gateway/chat.py` |
| **行** | 50 |
| **现状** | `body = await request.json()` 返回 `Any`,仅检查 `content` 非空。缺少类型校验、未知字段过滤 |
| **影响** | 畸形 JSON body 可能静默通过;多余字段被忽略但不报错 |
| **建议** | 用 Pydantic model 或至少 `body: dict = await request.json()` + try/except |

#### M10. gateway activity 同 M9

| 属性 | 详情 |
|------|------|
| **文件** | `services/gateway/activity.py` |
| **行** | 30 |
| **现状** | 同 M9,`await request.json()` 无校验 |

#### M11. 引擎持久化加载异常被静默吞掉

| 属性 | 详情 |
|------|------|
| **文件** | `services/graph/engines/python/engine.py` |
| **行** | 49-50 |
| **现状** | `except Exception: pass` 在加载持久化图数据时。文件损坏、格式错误、权限问题全部静默 |
| **影响** | 用户看不到任何错误提示,图谱空但引擎不报错 |
| **建议** | 至少 `logging.warning("图数据加载失败,从空图开始", exc_info=True)` |

#### M12. 引擎模块级单例

| 属性 | 详情 |
|------|------|
| **文件** | `services/graph/engines/python/engine.py` |
| **行** | 15-24 |
| **现状** | `_engine_singleton` + `threading.Lock` 全局单例模式 |
| **影响** | 测试间状态泄漏;无法并行测试不同配置的引擎实例 |
| **建议** | 改工厂模式或依赖注入 |

#### M13. browser _result_dict 误标为 async

| 属性 | 详情 |
|------|------|
| **文件** | `services/browser/capabilities.py` |
| **行** | 65-73 |
| **现状** | `_result_dict(result)` 是 `async def` 但函数体内无 `await` |
| **影响** | 不必要的协程包装;调用方需要 await 但实际是同步的 |
| **建议** | 改为普通 `def` |

#### M14. browser host 函数内 import

| 属性 | 详情 |
|------|------|
| **文件** | `services/browser/host.py` |
| **行** | 69-79 |
| **现状** | `_check_domain` 函数体内 import `ServiceError` 和 `urlparse` |
| **影响** | 每次调用重复 import;代码可读性差 |
| **建议** | 移至模块顶层 |

### Agent 层 (5 项)

#### M15. CheckpointStore.load 路径穿越

| 属性 | 详情 |
|------|------|
| **文件** | `agent/runtime/state.py` |
| **行** | 81-83 |
| **现状** | `run_id` 直接用于 `self._root / f"{run_id}.json"`,无校验。`run_id` 通常为 `uuid.uuid4().hex[:12]` 但 `load()` 方法不强制 |
| **影响** | 传入 `run_id="../../etc/passwd"` 可读取 checkpoint 目录外的文件 |
| **建议** | `if "/" in run_id or "\\" in run_id or ".." in run_id: raise ValueError(...)` |

#### M16. 使用 CPython 内部 Enum 属性

| 属性 | 详情 |
|------|------|
| **文件** | `agent/subagent/registry.py` |
| **行** | 35-39 |
| **现状** | `Mode._value2member_map_` 是 CPython 内部实现细节,未在 Python 文档中公开 |
| **影响** | CPython 版本升级可能移除或重命名此属性,导致运行时 AttributeError |
| **建议** | 用 `Mode.__members__` 或 `any(m.value == val for m in Mode)` |

#### M17. 访问 asyncio.Semaphore 内部属性

| 属性 | 详情 |
|------|------|
| **文件** | `agent/runtime/scheduler.py` |
| **行** | 21 |
| **现状** | `self._sem._value` 访问 Semaphore 的私有计数器 |
| **影响** | Python 版本升级可能改变内部实现 |
| **建议** | 维护独立的 `self._max_concurrent` 实例变量 |

#### M18. SQL LIKE 通配符未转义

| 属性 | 详情 |
|------|------|
| **文件** | `agent/memory/episodic.py` 行 62-63; `agent/memory/semantic.py` 行 68 |
| **现状** | `f"%{keyword}%"` 在 LIKE 模式中未转义 `%` 和 `_`。搜索 `100%` 会匹配 `1000` |
| **影响** | 搜索结果不准确(通配符被当作字面量的反面) |
| **建议** | `keyword.replace('%', '\\%').replace('_', '\\_')` + `ESCAPE '\\'` |

#### M19. Resource 维度在 PolicyEngine 中未执行

| 属性 | 详情 |
|------|------|
| **文件** | `agent/policy/engine.py` |
| **行** | 84-86 |
| **现状** | `decide()` 的 dispatch dict 只映射 `network` / `fs` / `app` / `shell`,不含 `resource`。`ResourcePolicy` 定义了 `max_rounds` / `max_tool_calls` / `max_subagents` / `daily_tokens` 但引擎从不检查 |
| **影响** | resource 维度的限制完全依赖执行点(modes.py、scheduler.py)自行检查,缺少统一的强制层 |
| **建议** | 添加 `_decide_resource` 方法,或文档说明 resource 是"软"维度,由执行点强制 |

---

## §5 LOW 级发现 (18 项)

| # | 层 | 文件 | 行 | 问题 | 影响 |
|---|---|------|---|------|------|
| L1 | platform | `platform/health/platform_health/monitor.py` | 72 | `start()` 无防重复调用,二次调用泄漏第一个 asyncio.Task | 资源泄漏 |
| L2 | platform | `platform/capability/platform_capability/guards.py` | 43-50 | `summarize_args` 子串匹配脱敏(`s in k.lower()`)可能过度(`my_token_count`)或不足(`cred` 不匹配 `credentials`) | 审计摘要精度 |
| L3 | platform | `platform/capability/platform_capability/gen_rest.py` | 56 | `globals()["Request"] = Request` 注入模块命名空间,FastAPI 内部变更时脆弱 | 可维护性 |
| L4 | platform | `platform/contracts/platform_contracts/events.py` | 80-88 | `Event.from_dict()` 缺键时裸 `KeyError`,应包装为 `ServiceError(INVALID_INPUT)` | 错误报告一致性 |
| L5 | platform | `platform/contracts/platform_contracts/events.py` | 35-36 | `ActorRef.scopes` 为 `tuple[str, ...]` 但未强制不可变(caller 可传 list) | 类型安全 |
| L6 | platform | `platform/settings/platform_settings/define.py` | 78-86 | Range 校验(`min`/`max`)仅对 INT/FLOAT 生效,STR/CHOICE 类型静默忽略 | 设置校验盲区 |
| L7 | services | `services/gateway/rest.py` | 41-45 | `lifespan`/`issuer`/`auth`/`quota`/`audit` 参数无类型或弱类型(`list | None`) | 静态分析盲区 |
| L8 | services | `services/sources/modules/repo/capabilities.py` | 33 | `workspace: Any` 注释写 `# Path` 但类型是 `Any`,丢失类型安全 | IDE 补全/类型检查 |
| L9 | services | `services/sources/modules/repo/capabilities.py` | 74-80 | 局部 import `ActorKind`/`ActorRef`/`Event`(已顶层导入,此处是死代码) | 代码可读性 |
| L10 | services | `services/sources/modules/news/store.py` | 74-84 | `html_to_text` 用 regex(`re.compile(r"<[^>]+>")`)解析 HTML,对畸形 HTML/实体/script 标签失效 | 摘要质量 |
| L11 | agent | `agent/master/master.py` | 45-48 | `Master.__init__` 的 `proactive`/`hooks`/`memory`/`subagents` 参数无类型注解 | 静态分析盲区 |
| L12 | agent | `agent/context/compressor.py` | 9-14 | `estimate_tokens` 用 `len(content) // 2` 粗略估算,纯英文高估 ~2x,CJK 可能低估 | 压缩触发时机不准 |
| L13 | agent | `agent/tools/web.py` | 18 | 每次 `web_fetch` 新建 `httpx.AsyncClient`,无连接池 | 多次抓取时连接开销 |
| L14 | agent | `agent/tools/base.py` | 104 | 工具参数直接传入 handler,未对 JSON Schema 做校验 | LLM 生成的畸形参数直接到达 handler |
| L15 | agent | `agent/master/proactive.py` | 93 | 主动消息含 emoji(`🙂`),违反 `agent/main.py:154` 的全局规则 | 规则一致性 |
| L16 | agent | `agent/skills/loader.py` | 29-33 | `full_text()` 每次调用 `rglob("SKILL.md")` 全量扫描文件系统 | 频繁调用时 I/O 开销 |
| L17 | agent | `agent/runtime/observability.py` | 47-72 | `metered_llm` 代理 duck-type LLMClient 但未声明实现 Protocol | 类型检查器无法验证 |
| L18 | deploy | `deploy/dev.py` | 26 | Windows 上 `web.terminate()` 不杀子进程(npm/node),Ctrl+C 后可能留孤儿进程 | 开发体验 |

---

## §6 脱耦矩阵验证

| 检查项 | 结果 | 证据 |
|--------|------|------|
| platform 不 import services/agent/apps | **PASS** | 全部 20 源文件扫描,零违规。依赖方向: contracts ← actor ← eventbus ← settings/health/secrets ← capability |
| platform 不含领域词汇/品牌名 | **PASS** | 全部使用通用术语(domain/service/capability/actor/registry) |
| 服务间互不 import | **PASS** | 12 服务扫描,零违规。需要其他领域数据时经 capability 调用 |
| 聚合服务子模块互不 import | **PASS** | sources/modules/repo、books、news 完全隔离;office/modules/doc、slides 完全隔离 |
| gateway 零业务逻辑 | **PASS** | gateway 仅做:事件路由 / SSE 推送 / 健康聚合 / 限流 / 行为上报入口 |
| agent 不直接 import services 实现 | **PASS** | 经 `deploy/bridge.py` 走 capability 框架;LLM 调用经 `deploy/llm_adapter.py` |
| agent 不直接写业务库表 | **PASS** | 全部经 capability `execute()` 守卫链 |
| 7 件套模板一致 | **PASS** | 10 个服务均 `wire()` → `Wiring`(registry + probe/start/stop/close) + `build_router(w.registry)` + `build_server(w.registry, ...)` |
| 文件 ≤300 行 | **FAIL** | 4 文件超限: indexer.py(1162)、engine.py(742)、graph/store.py(362)、engines/store.py(355) |
| 品牌名零出现 | **PASS** | 目录名/文件名/变量名/函数名/配置键均按功能命名 |

---

## §7 安全检查验证

| 检查项 | 结果 | 详情 |
|--------|------|------|
| SQL 注入 | **PASS** | 全部查询参数化(`?` 占位符);2 处 f-string SQL(`repo/store.py` ORDER BY、`graph/store.py` SELECT cols)有白名单保护 |
| 路径穿越 (agent fs jail) | **PASS** | `agent/tools/fs.py` 双层防护: `_resolve()` 做 `Path.resolve()` + containment 检查;`Toolbelt` 再过 PolicyEngine |
| 路径穿越 (books add_book) | **FAIL** | `title` 参数未消毒,可写到 workspace 外(H6) |
| 路径穿越 (checkpoint load) | **FAIL** | `run_id` 未校验,可穿越到 checkpoint 目录外(M15) |
| SSRF (news fetch) | **FAIL** | 无域名白名单、无内网 IP 拒绝(C3) |
| SSRF (web_fetch 重定向) | **FAIL** | `follow_redirects=True`,重定向目标不二次校验(H1) |
| SSRF (policy URL 解析) | **FAIL** | `split("/")[2]` 可被 userinfo URL 绕过(H2) |
| Secret 处理 | **PASS** | SecretStore 加密落盘(Fernet);`has_api_key` 模式不泄露 key;`set_api_key` + `set_github_token` 两层 USER-only 强制 |
| 命令注入 | **可控** | L2 用户确认 + PolicyEngine 四维判定;但无命令黑名单(H3) |
| 审计脱敏 | **PASS** | `SENSITIVE_KEYS` 子串匹配(api_key/apikey/token/secret/password/authorization) + 截断 200 字符 |
| 鉴权 | **PASS** | LocalAuth: USER 恒可信;AGENT/EXTERNAL 需 scope;agent 持自己的 ActorRef,与用户走同一套 |
| 凭证传递 | **PASS** | `ActorContext(actor, scopes, trace_id)` 沿链传递,任何环节不得提权 |
| 输入校验(capability 层) | **PASS** | `coerce_input()` 校验未知字段、必填字段、浅层类型(bool/int/float/str/list/dict) |
| 速率限制 | **PASS** | gateway `RateLimiter` 按 actor 限流 + SSE 连接数上限;capability `CostQuota` 按日配额扣减 |

---

## §8 架构亮点(值得保持的设计)

1. **"一次定义,双协议生成"**: `platform_capability` 注册表 → REST router + FastMCP tools 零手写第二份。新增能力 = 注册表新增条目,REST / MCP / agent 三处零改动
2. **Toolbelt.trimmed() 能力面裁剪**: 派出 subagent 时经白名单做真正的工具裁剪——"不能写文件"是不给 write 工具,不是提示词约束
3. **事件持久化先于推送**: EventBus 先落日志(事实来源)再直推进程内订阅者;订阅者掉队(队列满)只置 lagged 标记,从日志补齐,不丢事件
4. **Secret 边界双层强制**: 框架层(platform/guards.py LocalAuth) + 服务层(llm capabilities.py `set_api_key` 检查 `_actor.kind is not ActorKind.USER`),铁律 7 隐私例外落地
5. **按需加载体系**: `list_notes` 只返摘要(标题/标签/更新时间)、`get_note` 按需取全文;sources 同理——token 友好
6. **故障隔离**: 每服务独立 Wiring(registry + probe/start/stop/close),单服务崩溃不影响其余;健康探测 + 统一错误码 + 页面降级态
7. **注释质量**: §X.Y 引用贯穿全代码(如 `# §7.3`、`# §9.20`);模块级 docstring 说明架构定位与演进;中文注释一致性极高
8. **部署形态灵活**: 同一个 `wire()` 函数同时支持独立运行(`uvicorn services.<x>.rest:app_factory`)和聚合运行(`deploy/backend.py` 的 MountSpec 挂载),接口与协议完全一致
9. **Bridge 闭包绑定**: `deploy/bridge.py` 的 handler 用默认参数绑定(`_reg=m.registry, _cap=cap`)避免闭包陷阱,每次迭代正确绑定当次注册表与能力

---

## §9 修复优先级建议

| 优先级 | 项 | 预估工作量 | 说明 |
|--------|----|-----------|------|
| **P0 安全** | C3(新闻 SSRF) + H1(web 重定向 SSRF) + H2(policy URL 解析) + H6(书籍路径穿越) | 1-2h | 4 个安全边界修复,每个 ≤20 行改动 |
| **P1 可靠性** | H7(task 引用) + H8(Content-Length 上限) + H9(INSERT OR REPLACE) + M15(checkpoint 路径穿越) | 1h | 数据完整性与进程健壮性 |
| **P2 架构规范** | C1(indexer 拆分) + C2(engine 拆分) + H4/H5(store 拆分) | 3-4h | 4 个文件超限修复,纯重构无功能变更 |
| **P3 代码质量** | 其余 20 MEDIUM + 18 LOW | 逐步修复 | 类型注解补全、重复代码消除、内部 API 替换等 |

---

*审计完成于 2026-08-25。共审查 ~150 个 Python 源文件,覆盖 platform / services / agent / deploy 全部后端代码。*
