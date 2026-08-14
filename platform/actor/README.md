# platform/actor — actor 与鉴权

- Actor 模型:`{ kind: user | agent | external, id, scopes[] }`(契约见 platform_contracts);
- 本机鉴权:首次启动生成本机密钥,签发/校验 HMAC 会话令牌;
- **agent 无后门**:agent 持自己的 actor 凭证,与用户走同一套校验;
- 凭证传递:`ActorContext` 沿调用链传递,`restrict()` 只能收窄,任何环节不得提权。

外部 MCP client 的 OAuth 2.1 / 静态令牌签发在后续步骤接入(见 docs/architecture.md §7.4)。
