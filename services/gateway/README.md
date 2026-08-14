# services/gateway — 聚合入口(骨架)

对 apps 的唯一入口(§6.3):路由聚合、本机令牌校验、SSE 汇聚(chat 通道)、
各服务设置 schema 的聚合读取、**健康探测与统一错误码出口**(§7.10)。
web 只需知道 gateway 一个地址。
