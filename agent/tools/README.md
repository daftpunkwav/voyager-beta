# agent/tools — agent 自身工具(骨架)

不经领域服务的内部工具:ask_user(询问用户,§9.15)、request_context(向 master
申请上下文,§9.6)、spawn_subagent、reach_out(主动发消息,§9.8)、load_skill、
recall_memory、fs(jail + policy)、shell(policy)、web(网络权限层)。§9.4。

activate.py:可激活域从当前名册 `__` 前缀现算(`domain_prefixes`),页面
预激活名单(`page_preactivate`,仅 notes/graph/sources 三页)也在该文件。
