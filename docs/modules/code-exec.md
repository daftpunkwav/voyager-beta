# code-exec 模块卡

- **职责**:在容器沙箱中执行代码文件/片段。不做:持久环境状态(一次性容器)。
- **架构锚点**:§8.5
- **能力**(初始集):`run_file / run_snippet / list_runtimes`
- **事件**:`task.progress / task.completed / task.failed`
- **设置项**:`code-exec.runtimes.*`(镜像/限额)/ `code-exec.network`(默认关)
- **数据**:挂载 workspace/sandbox/;结果经事件与产物文件
- **依赖**:platform + 容器运行时(docker)
- **状态**:骨架
