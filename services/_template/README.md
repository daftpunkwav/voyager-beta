# services/_template — 新领域服务脚手架

复制本目录即得一个新服务(验收标准:不触碰任何其他目录,§13.1):

1. `cp -r services/_template services/<domain>`,全局替换 `template` 为 `<domain>`;
2. 在根 `pyproject.toml` 的 `tool.uv.workspace.members` 加入 `services/<domain>`,
   并在 `tool.uv.sources` 声明,然后 `uv sync --all-packages`;
3. 在 `capabilities.py` 注册本领域能力(初始最小集,完整清单写进 `docs/modules/<domain>.md`);
4. 长任务:handler 只入队返回 `JobRef`(§7.3),进度经事件流,见 `worker.py` 示例;
5. 端口在 `service.json` 声明,向 gateway 登记。

六件套:`capabilities.py`(注册表,单一事实来源)/ `rest.py` / `mcp_server.py` /
`worker.py`(无长任务可删)/ `store.py` / `settings.py` + `service.json` + `tests/`。
