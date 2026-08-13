import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);
const reactDir = path.dirname(require.resolve('react/package.json'));
const reactDomDir = path.dirname(require.resolve('react-dom/package.json'));

// 后端默认 CORS 白名单端口（services/api/backend/config.py cors_allow_origins）。
// 仅「直连跨源」模式（VITE_API_BASE_URL 非空）依赖 CORS；同源代理模式不受影响。
const DEFAULT_CORS_PORTS = [5173, 5174, 5175, 4173, 5193];

// 自定义 VITE_PORT 不在后端 CORS 白名单时的启动提示
const vitePort = process.env.VITE_PORT ? Number(process.env.VITE_PORT) : undefined;
if (vitePort && !DEFAULT_CORS_PORTS.includes(vitePort)) {
  console.warn(
    `[vite] VITE_PORT=${vitePort} 不在后端 CORS 白名单（${DEFAULT_CORS_PORTS.join('/')}）。` +
      `同源代理模式（VITE_API_BASE_URL 留空）无影响；若用 VITE_API_BASE_URL 直连后端，` +
      `必须把 http://127.0.0.1:${vitePort} 加入 services/api/backend/config.py 的 cors_allow_origins。`,
  );
}

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      types: path.resolve(__dirname, '../../packages/types/src/index.ts'),
      // 保证全应用使用同一份 React（避免 monorepo hoist 到 React 18）
      react: reactDir,
      'react-dom': reactDomDir,
    },
    dedupe: ['react', 'react-dom', '@tanstack/react-query'],
  },
  server: {
    host: '127.0.0.1',
    // 支持 VITE_PORT / VITE_API_TARGET 环境变量覆盖（默认与后端 npm run dev:api 一致）
    port: vitePort || 5173,
    strictPort: true, // 端口被占用直接报错，避免静默顺延后 CORS/文案断链
    proxy: {
      // 19876 在部分 Windows 环境会出现幽灵 LISTENING；开发暂用 19878
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:19878',
        changeOrigin: true,
      },
      // 后端 /health 不在 /api 前缀下，需单独代理（EmbedAgentChat 挂载探测依赖它）
      '/health': {
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:19878',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './tests/setup.ts',
    include: ['tests/unit/**/*.test.{ts,tsx}'],
  },
});
