# services/code-exec — 代码执行(骨架)

容器沙箱为最终形态(决策 §15):每次执行起一次性容器,挂载 workspace/sandbox/,
无网络(显式开通除外),资源限额为设置项。首批语言 Python / Node / Shell。
能力(初始集):run_file / run_snippet / list_runtimes。§8.5。
