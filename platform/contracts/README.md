# platform/contracts — 契约包

跨模块共享的**纯类型**层:事件信封、capability 输入输出 DTO、统一错误码、协议版本。

铁律(见 docs/architecture.md §7.1):

- 纯类型,零逻辑,**零第三方依赖**;
- 唯一直接被 apps / agent / services 三方引用的包;
- 前端 TS 类型由本包生成,三方认知一致;
- 协议变更升 `version.py` 中的 `PROTOCOL_VERSION`。

import 名为 `platform_contracts`(避免与标准库 `platform` 冲突)。
