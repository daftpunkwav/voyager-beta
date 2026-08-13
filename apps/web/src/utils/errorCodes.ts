/**
 * 报错码映射表 —— 与 docs/architecture/decoupling/ERROR_CODES.md 同步。
 * 后端常量见 services/api/backend/core/error_codes.py。
 */

export type ErrorSeverity = 'error' | 'warning' | 'info';

export interface ErrorCodeDesc {
  title: string;
  hint: string;
  severity: ErrorSeverity;
}

export const ERROR_CODES: Record<string, ErrorCodeDesc> = {
  // 模块 / 系统
  MODULE_LOAD_FAILED: {
    title: '模块加载失败',
    hint: '某后端模块启动异常；查看 /health 与后端日志',
    severity: 'error',
  },
  SYSTEM_SECRET_KEY_WEAK: {
    title: '密钥强度不足',
    hint: 'SECRET_KEY 过短，请生成强随机密钥',
    severity: 'error',
  },
  SYSTEM_INTERNAL_ERROR: {
    title: '内部错误',
    hint: '未分类异常，请查看后端日志',
    severity: 'error',
  },
  RATE_LIMITED: {
    title: '请求过于频繁',
    hint: '请稍后重试',
    severity: 'warning',
  },
  VALIDATION_ERROR: {
    title: '参数校验失败',
    hint: '请求参数不符合要求',
    severity: 'warning',
  },
  API_ERROR: {
    title: '请求失败',
    hint: '网络或未结构化错误，请稍后重试',
    severity: 'error',
  },

  // Agent
  AGENT_MODULE_DOWN: {
    title: 'Agent 模块未就绪',
    hint: 'Agent 服务启动失败，请检查日志或重启',
    severity: 'error',
  },
  AGENT_LLM_UNAVAILABLE: {
    title: 'Agent 服务暂不可用',
    hint: '未配置 LLM API Key 或连接失败，已切换手动模式',
    severity: 'warning',
  },
  AGENT_MISCONFIGURED: {
    title: 'Agent 进程配置错误',
    hint: '已配置 AGENT_BASE_URL 但缺少内部令牌',
    severity: 'error',
  },
  AGENT_TOKEN_UNSET: {
    title: 'Agent 内部令牌未配置',
    hint: '请在 Agent 进程设置 agent_internal_token',
    severity: 'error',
  },
  AGENT_UNAUTHORIZED: {
    title: 'Agent 内部鉴权失败',
    hint: 'API 与 Agent 令牌不一致',
    severity: 'error',
  },
  AGENT_PROXY_ERROR: {
    title: 'Agent 代理转发失败',
    hint: '无法连接独立 Agent 进程',
    severity: 'error',
  },
  AGENT_SESSION_NOT_FOUND: {
    title: '会话不存在',
    hint: '会话 ID 错误或已删除',
    severity: 'error',
  },
  AGENT_SESSION_PROJECT_DENIED: {
    title: '无法绑定项目到会话',
    hint: '项目不存在或 ID 错误',
    severity: 'error',
  },
  AGENT_INVALID_ID: {
    title: '未知或非法 Agent',
    hint: 'agent_id 不在注册表中',
    severity: 'error',
  },
  AGENT_CHAT_FAILED: {
    title: '对话失败',
    hint: 'Agent 对话异常，请稍后重试',
    severity: 'error',
  },
  AGENT_ANALYZE_FAILED: {
    title: '项目分析失败',
    hint: '分析过程异常，请查看日志或稍后重试',
    severity: 'error',
  },
  AGENT_IMPORT_ASSIST_FAILED: {
    title: '导入助手失败',
    hint: '助手不可用，可继续手动导入',
    severity: 'warning',
  },
  AGENT_TRENDING_FAILED: {
    title: '趋势扫描失败',
    hint: 'GitHub API 限流或 LLM 失败',
    severity: 'error',
  },
  AGENT_CLASSIFY_FAILED: {
    title: '分类失败',
    hint: '自动分类异常，可手动设置分类',
    severity: 'error',
  },
  AGENT_NOTE_FAILED: {
    title: '笔记生成失败',
    hint: '自动生成笔记异常，可手动编写',
    severity: 'error',
  },
  AGENT_DISPATCH_FAILED: {
    title: '专家调度失败',
    hint: 'Hub 派发子 Agent 失败，请查看日志',
    severity: 'error',
  },
  AGENT_TOOL_DENIED: {
    title: '工具权限未开启',
    hint: '请在设置中开启对应 Agent 权限',
    severity: 'warning',
  },
  AGENT_TOOL_TIMEOUT: {
    title: '工具执行超时',
    hint: '外部 API 过慢或超时设置过短',
    severity: 'warning',
  },
  AGENT_TOOL_FAILED: {
    title: '工具执行失败',
    hint: '工具返回错误，请查看详情',
    severity: 'error',
  },

  // LLM
  LLM_KEY_MISSING: {
    title: '未配置 LLM Key',
    hint: '请前往设置页配置 API Key',
    severity: 'warning',
  },
  LLM_DECRYPT_FAILED: {
    title: 'LLM Key 解密失败',
    hint: '密钥变更导致密文无法解密；请重新配置 Key',
    severity: 'error',
  },
  LLM_REQUEST_FAILED: {
    title: 'LLM 请求失败',
    hint: '上游模型调用失败，请检查 base URL 与模型名',
    severity: 'error',
  },
  LLM_TIMEOUT: {
    title: 'LLM 超时',
    hint: '模型响应过慢，请稍后重试或更换模型',
    severity: 'warning',
  },
  LLM_RATE_LIMITED: {
    title: 'LLM 上游限流',
    hint: '供应商配额不足，请稍后重试',
    severity: 'warning',
  },

  // Graph
  GRAPH_MODULE_DOWN: {
    title: '图谱模块未就绪',
    hint: '图谱服务不可用，项目/笔记功能不受影响',
    severity: 'warning',
  },
  GRAPH_NOT_INDEXED: {
    title: '项目尚未索引',
    hint: '请先构建代码图谱',
    severity: 'info',
  },
  GRAPH_INDEX_FAILED: {
    title: '图谱索引失败',
    hint: '索引管线异常，请查看日志',
    severity: 'error',
  },
  GRAPH_QUERY_FAILED: {
    title: '图谱查询失败',
    hint: '相似度或邻居查询异常',
    severity: 'error',
  },
  GRAPH_ENGINE_UNAVAILABLE: {
    title: '图谱引擎不可用',
    hint: '自托管图谱引擎未启动或连接失败，请检查 graph_engine 服务',
    severity: 'error',
  },
  GRAPH_L1_MODULE_DOWN: {
    title: 'L1 代码图谱模块未就绪',
    hint: 'L1 索引/渲染管线异常，请查看 graph_engine 日志',
    severity: 'error',
  },
  LLM_USAGE_MODULE_DOWN: {
    title: 'LLM 用量统计模块不可用',
    hint: '用量统计服务异常，不影响 Agent 功能，请查看后端日志',
    severity: 'warning',
  },

  // Project / Note / Category / Tag
  PROJECT_NOT_FOUND: {
    title: '项目不存在',
    hint: '项目 ID 错误或不存在',
    severity: 'error',
  },
  PROJECT_URL_INVALID: {
    title: '仓库 URL 无效',
    hint: '请使用 https://github.com/owner/repo 格式',
    severity: 'warning',
  },
  PROJECT_URL_DUPLICATE: {
    title: '仓库已导入',
    hint: '该 URL 已在项目库中',
    severity: 'warning',
  },
  PROJECT_IMPORT_FAILED: {
    title: '批量导入失败',
    hint: '部分或全部仓库导入失败',
    severity: 'error',
  },
  NOTE_NOT_FOUND: {
    title: '笔记不存在',
    hint: '笔记 ID 错误或不存在',
    severity: 'error',
  },
  CATEGORY_NOT_FOUND: {
    title: '分类不存在',
    hint: '分类 ID 错误或不存在',
    severity: 'error',
  },
  CATEGORY_PRESET_IMMUTABLE: {
    title: '预设分类不可改',
    hint: '系统预设分类不可重命名或删除',
    severity: 'warning',
  },
  CATEGORY_NAME_DUPLICATE: {
    title: '分类名重复',
    hint: '请更换分类名称',
    severity: 'warning',
  },
  TAG_NOT_FOUND: {
    title: '标签不存在',
    hint: '标签 ID 错误或不存在',
    severity: 'error',
  },
  TAG_NAME_DUPLICATE: {
    title: '标签名重复',
    hint: '请更换标签名称',
    severity: 'warning',
  },

  // GitHub
  GITHUB_NOT_BOUND: {
    title: '未绑定 GitHub',
    hint: '请先在设置中绑定账号',
    severity: 'warning',
  },
  GITHUB_ACCOUNT_NOT_FOUND: {
    title: 'GitHub 账号不存在',
    hint: '绑定记录 ID 错误',
    severity: 'error',
  },
  GITHUB_PAT_INVALID: {
    title: 'GitHub PAT 无效',
    hint: 'PAT 已过期或无权限；请重新绑定',
    severity: 'error',
  },
  GITHUB_AUTH_FAILED: {
    title: 'GitHub 鉴权失败',
    hint: 'PAT 无效或权限不足；请重新绑定',
    severity: 'error',
  },
  GITHUB_API_RATE_LIMIT: {
    title: 'GitHub API 限流',
    hint: '匿名请求超额；配置 GitHub PAT 提升配额',
    severity: 'warning',
  },
  GITHUB_API_FAILED: {
    title: 'GitHub API 调用失败',
    hint: '上游返回错误，请稍后重试',
    severity: 'error',
  },
  GITHUB_STARS_FETCH_FAILED: {
    title: 'Stars 拉取失败',
    hint: '无法获取 Star 列表，请检查网络与 PAT',
    severity: 'error',
  },

  // Profile / Settings
  PROFILE_NOT_FOUND: {
    title: '学习者画像不存在',
    hint: '画像单例异常，请重启应用',
    severity: 'error',
  },
  MEMORY_PROPOSAL_NOT_FOUND: {
    title: '记忆提案不存在',
    hint: '提案 ID 错误或已处理',
    severity: 'error',
  },
  SETTINGS_UPDATE_FAILED: {
    title: '设置保存失败',
    hint: '写入设置异常，请查看日志',
    severity: 'error',
  },
  SETTINGS_LLM_BASE_INVALID: {
    title: 'LLM API Base 不安全',
    hint: '地址被 SSRF 校验拒绝，请使用公网 HTTPS',
    severity: 'warning',
  },
};

const FALLBACK: ErrorCodeDesc = {
  title: '发生错误',
  hint: '请稍后重试或查看日志',
  severity: 'error',
};

export function describeError(code: string): ErrorCodeDesc {
  return ERROR_CODES[code] ?? FALLBACK;
}

/** 生成 toast 展示文案：[CODE] 标题 */
export function formatErrorToast(code: string, fallbackMessage?: string): string {
  const desc = describeError(code);
  const title = ERROR_CODES[code] ? desc.title : (fallbackMessage || desc.title);
  return `[${code}] ${title}`;
}
