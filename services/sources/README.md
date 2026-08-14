# services/sources — 资源聚合服务(骨架)

统一管理"可学习的资源"(§8.2)。聚合服务内部同样脱耦:每种资源类型是
`modules/` 下的自包含子模块(自己的 capabilities/store/worker),
聚合层只做注册表合并与类型分发,子模块之间互不 import。
新增类型 = `modules/` 下新增自包含目录,聚合层零改动。
