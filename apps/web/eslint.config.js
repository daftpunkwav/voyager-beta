import js from '@eslint/js';
import globals from 'globals';
import tsParser from '@typescript-eslint/parser';
import tsPlugin from '@typescript-eslint/eslint-plugin';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';

export default [
  { ignores: ['dist/**', 'node_modules/**'] },
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: globals.browser,
      parser: tsParser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      '@typescript-eslint': tsPlugin,
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...js.configs.recommended.rules,
      ...tsPlugin.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      // React 19 自动 JSX 运行时；类型注解仍可能引用 React 命名空间
      'no-undef': 'off',
      // React Compiler 规则与 R3F「渲染后改共享对象」惯用法冲突：
      // EdgeLines/NodeCloud 在渲染后修改 uniform.value / raycaster.params，
      // UniverseGraphView 的手动 useMemo 属性能优化。与下方 set-state-in-effect
      // / purity / refs 关闭理由一致（v7 严格规则在原型阶段过激）。
      'react-hooks/immutability': 'off',
      'react-hooks/preserve-manual-memoization': 'off',
      // v7 新增的严格规则在 v1 原型阶段过于激进，保持与旧 .eslintrc 等效
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/purity': 'off',
      'react-hooks/refs': 'off',
      'react-refresh/only-export-components': 'off',
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-non-null-assertion': 'error',
      // 兼容层桥接(legacyApi / types.IApiClient)需 any 推断:旧 store 直接 .data 访问;
      // 旧 async generator 在新事件流下不再 yield,需 require-yield 关闭。
      'no-constant-condition': 'error',
      'require-yield': 'error',
      // 迁移期:上游迁入的 page / component / util / store 暂以 @ts-nocheck 标注,
      // 全部带说明(上游迁移代码,字段重命名由 legacyApi 边界归一化);
      // 新 page / hook / store 仍按 strict 写(见各文件顶部注释)。
      '@typescript-eslint/ban-ts-comment': [
        'error',
        {
          'ts-nocheck': 'allow-with-description',
          'ts-ignore': true,
          'ts-expect-error': 'allow-with-description',
          'ts-check': false,
        },
      ],
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      'no-unused-vars': 'off',
      // §4.2.15: 禁止直接使用 dangerouslySetInnerHTML；先 DOMPurify.sanitize
      'no-restricted-syntax': [
        'error',
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message: 'dangerouslySetInnerHTML 必须先经 DOMPurify.sanitize 再渲染（MermaidBlock.tsx 已示范）。',
        },
      ],
    },
  },
  // 数据门面单点(非页面文件):业务代码禁止绕过 @/api/client 直引实现层。
  // 注意:flat config 中同规则后块覆盖前块,故按文件集拆两块、各自持有完整 pattern 集,
  // pages 的规则见下一块(含跨页互引限制),两块文件集互斥。
  {
    files: ['src/**/*.{ts,tsx}'],
    ignores: ['src/pages/**', 'src/api/client.ts', 'src/api/types.ts', 'src/bridge/legacyApi.ts'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['@/bridge/legacyApi'],
              message: '数据门面单一入口:@/api/client(getApi)。实现层 bridge/legacyApi 不得被业务直接引用。',
            },
            {
              group: ['@/api/real', '@/api/real/*'],
              message: '@/api/real 已删除;改用 getApi() 或 callCapability。',
            },
          ],
        },
      ],
    },
  },
  // 共享层不得反向依赖页面模块(MarkdownRenderer / hooks / stores)
  {
    files: [
      'src/components/common/**/*.{ts,tsx}',
      'src/hooks/**/*.{ts,tsx}',
      'src/stores/**/*.{ts,tsx}',
    ],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['@/pages/*'],
              message: '共享层不得 import 页面模块(§10.1);页面私有逻辑经 props/bridge 注入。',
            },
            {
              group: ['@/bridge/legacyApi'],
              message: '数据门面单一入口:@/api/client(getApi)。实现层 bridge/legacyApi 不得被业务直接引用。',
            },
            {
              group: ['@/api/real', '@/api/real/*'],
              message: '@/api/real 已删除;改用 getApi() 或 callCapability。',
            },
          ],
        },
      ],
    },
  },
  // pages 专属:跨页互引禁令 + 与全局相同的门面单点限制(flat config 需整集重申)。
  // §10.1 页面即模块:page 目录之间互不 import;共享只经 bridge/contracts/基础 UI。
  {
    files: ['src/pages/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['@/pages/*'],
              message: '页面之间互不 import(§10.1 铁律 1);共享物只能经 bridge/contracts/基础 UI 包。',
            },
            {
              group: ['@/bridge/legacyApi'],
              message: '数据门面单一入口:@/api/client(getApi)。实现层 bridge/legacyApi 不得被业务直接引用。',
            },
            {
              group: ['@/api/real', '@/api/real/*'],
              message: '@/api/real 已删除;改用 getApi() 或 callCapability。',
            },
          ],
        },
      ],
    },
  },
  // 兼容层 + R3F / Three 场景豁免区:
  //  - bridge/legacyApi.ts 与 api/types.ts 需 any(legacyApi 边界归一化);
  //  - 旧 async generator 在新事件流下不 yield,允许 require-yield 关闭;
  //  - code-graph / graph 子目录就地改 uniforms、用 @ts-nocheck;布局算法用非空断言。
  {
    files: [
      'src/bridge/legacyApi.ts',
      'src/api/types.ts',
      'src/components/code-graph/**/*.{ts,tsx}',
      'src/components/graph/**/*.{ts,tsx}',
    ],
    rules: {
      '@typescript-eslint/ban-ts-comment': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-non-null-assertion': 'off',
      'no-constant-condition': 'off',
      'require-yield': 'off',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      'react-hooks/immutability': 'off',
    },
  },
];
