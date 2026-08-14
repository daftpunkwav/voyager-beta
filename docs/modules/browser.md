# browser 模块卡

- **职责**:浏览器自动化指令的下发与结果回收;宿主在 desktop(§8.7)。
  不做:页面业务理解(agent 的事)。
- **架构锚点**:§8.7、§9.16
- **能力**(初始集 → 规划):navigate / click / type / read / screenshot……
  一切出网经网络权限层(§9.9)
- **事件**:执行结果与页面状态回报
- **设置项**:`browser.headless`、`browser.allowed_domains`(默认继承 agent 网络权限)
- **数据**:无持久化;截图等落 workspace/
- **依赖**:platform + apps/desktop/browser-host
- **状态**:骨架
