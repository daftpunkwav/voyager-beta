# agent/runtime — 运行时底座(骨架)

十二项职责(§9.1):事件循环 loop.py / 调度 scheduler.py / 状态 state.py /
容错 recovery.py / runtime 事件 events.py / 观测 observability.py。
loop 的领域 handler 绑定与 hook relay 在 wire.py(bind_event_loop,phase-28)。
