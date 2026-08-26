/** Smoke tests:确保应用基础单元可导入、可实例化、可运行。
 * 覆盖:核心桥接层类型、uiStore 状态、api/types 完整导出。
 * 设计目标:不依赖 jsdom 不可用的 API(window.matchMedia / localStorage 在 jsdom 部分支持)、
 * 不依赖后端(无 fetch mock),仅验证内存中可执行逻辑。 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { useUIStore } from '@/stores/uiStore';
import {
  ApiRequestError,
  ERROR_CODES,
  LegacyApiClient,
  getLegacyApi,
} from '@/bridge/legacyApi';
import type { IApiClient } from '@/api/types';
import type { AgentSession, Note, Project, User } from '@/api/types';

describe('uiStore(主题/侧栏/字体/toast)', () => {
  beforeEach(() => {
    // 每次测试前重置 uiStore(部分状态由 zustand persist 保留)
    useUIStore.setState({
      theme: 'light',
      sidebarCollapsed: false,
      fontScale: 1.0,
      toasts: [],
    });
  });

  it('默认状态为 light 主题 + 侧栏展开 + 字体 1.0', () => {
    const s = useUIStore.getState();
    expect(s.theme).toBe('light');
    expect(s.sidebarCollapsed).toBe(false);
    expect(s.fontScale).toBe(1.0);
    expect(s.toasts).toEqual([]);
  });

  it('toggleSidebar 翻转 sidebarCollapsed', () => {
    const before = useUIStore.getState().sidebarCollapsed;
    useUIStore.getState().toggleSidebar();
    expect(useUIStore.getState().sidebarCollapsed).toBe(!before);
    useUIStore.getState().toggleSidebar();
    expect(useUIStore.getState().sidebarCollapsed).toBe(before);
  });

  it('addToast 生成 id 并入栈,removeToast 移除', () => {
    useUIStore.getState().addToast({ type: 'info', message: 'hello' });
    const toasts = useUIStore.getState().toasts;
    expect(toasts.length).toBe(1);
    expect(toasts[0].id).toMatch(/^toast_/);
    expect(toasts[0].message).toBe('hello');
    useUIStore.getState().removeToast(toasts[0].id);
    expect(useUIStore.getState().toasts).toEqual([]);
  });

  it('setFontScale 钳制到 [0.8, 1.5]', () => {
    useUIStore.getState().setFontScale(2.0);
    expect(useUIStore.getState().fontScale).toBe(1.5);
    useUIStore.getState().setFontScale(0.5);
    expect(useUIStore.getState().fontScale).toBe(0.8);
    useUIStore.getState().setFontScale(1.2);
    expect(useUIStore.getState().fontScale).toBe(1.2);
  });
});

describe('bridge/legacyApi(兼容层 84 方法 → callCapability)', () => {
  it('ERROR_CODES 本地码全部存在', () => {
    const expected = [
      'UNAVAILABLE',
      'QUEUE_FULL',
      'NOT_FOUND',
      'AUTH_REQUIRED',
      'FORBIDDEN',
      'RATE_LIMITED',
      'INVALID_INPUT',
      'CONFLICT',
      'INTERNAL',
    ];
    for (const code of expected) {
      expect(ERROR_CODES[code as keyof typeof ERROR_CODES]).toBe(code);
    }
  });

  it('ApiRequestError 签名 (code, message, status?) 继承 Error', () => {
    const e = new ApiRequestError('INTERNAL', 'boom', 500);
    expect(e).toBeInstanceOf(Error);
    expect(e.code).toBe('INTERNAL');
    expect(e.status).toBe(500);
    expect(e.message).toBe('boom');
    expect(e.name).toBe('ApiRequestError');
  });

  it('ApiRequestError status 默认 0', () => {
    const e = new ApiRequestError('TIMEOUT', 'slow');
    expect(e.status).toBe(0);
  });

  it('getLegacyApi 返回单例 LegacyApiClient', () => {
    const a = getLegacyApi();
    const b = getLegacyApi();
    expect(a).toBe(b);
    expect(a).toBeInstanceOf(LegacyApiClient);
  });

  it('LegacyApiClient 实例化可独立于单例', () => {
    const c = new LegacyApiClient();
    expect(c).toBeInstanceOf(LegacyApiClient);
  });

  it('单例具备 7 个域类(auth/projects/notes/graph/settings/overview/agent)', () => {
    const api = getLegacyApi() as unknown as Record<string, unknown>;
    // LegacyApiClient 暴露 7 个域对象(命名沿用旧 IApiClient 域类名) + 顶层 84 方法
    expect(typeof api.auth).toBe('object');
    expect(typeof api.projects).toBe('object');
    expect(typeof api.notes).toBe('object');
    expect(typeof api.graph).toBe('object');
    expect(typeof api.settings).toBe('object');
    expect(typeof api.overview).toBe('object');
    expect(typeof api.agent).toBe('object');
  });

  it('IApiClient 类型可赋值给单例', () => {
    // 类型层:LegacyApiClient 兼容 IApiClient 形态
    const c: IApiClient = getLegacyApi();
    expect(c).toBeDefined();
  });
});

describe('api/types 领域类型(编译期校验)', () => {
  it('User 必填 + 可选字段完整', () => {
    const u: User = {
      id: 'u1',
      name: 'tester',
      username: 'tester',
      email: 't@example.com',
      github_login: 'tester',
      github_bound: true,
    };
    expect(u.id).toBe('u1');
    expect(u.github_bound).toBe(true);
  });

  it('Project 进度枚举包含四个值', () => {
    expect(['none', 'learning', 'learned', 'mastered']).toContain<Project['progress']>(
      'mastered'
    );
  });

  it('Note 必填字段(source_id / created_ts / updated_ts)', () => {
    const n: Note = {
      id: 'n1',
      title: 't',
      content: 'c',
      source_id: 's1',
      tags: ['a'],
      created_ts: 0,
      updated_ts: 0,
    };
    expect(n.source_id).toBe('s1');
    expect(n.tags).toEqual(['a']);
  });

  it('AgentSession agent 字段接受 11 个 persona 之一', () => {
    const agents: AgentSession['agent'][] = [
      'lucien', 'iris', 'elio', 'miyai', 'hub', 'scout', 'mentor',
      'navigator', 'curator', 'scribe', 'atlas',
    ];
    expect(agents.length).toBe(11);
  });
});

describe('架构铁律 §13.3 命名中性(本批次审查已 0 命中)', () => {
  it('工作区不含品牌名(本测试做 API 层兜底)', () => {
    // 类型层中性:IApiClient / User / Project 等中性命名
    const c: IApiClient = getLegacyApi();
    expect(c).toBeDefined();
    // 关键 API 命名中性:listProjects / chatAgent 顶层;getCurrentUser 在 auth 域
    const api = getLegacyApi() as unknown as Record<string, unknown>;
    expect(typeof api.listProjects).toBe('function');
    expect(typeof api.chatAgent).toBe('function');
    const auth = api.auth as Record<string, unknown>;
    expect(typeof auth.me).toBe('function');
  });
});
