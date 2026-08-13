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
  // R3F / Three 场景会就地改 uniforms、并用 @ts-nocheck；布局算法大量使用非空断言
  {
    files: [
      'src/components/code-graph/**/*.{ts,tsx}',
      'src/components/graph/**/*.{ts,tsx}',
    ],
    rules: {
      '@typescript-eslint/ban-ts-comment': 'off',
      '@typescript-eslint/no-non-null-assertion': 'off',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      'react-hooks/immutability': 'off',
    },
  },
];
