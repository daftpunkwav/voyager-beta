import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);
const reactDir = path.dirname(require.resolve('react/package.json'));
const reactDomDir = path.dirname(require.resolve('react-dom/package.json'));

const BACKEND = process.env.VITE_API_TARGET || 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      // 保证全应用使用同一份 React(避免 monorepo hoist 出现双实例)
      react: reactDir,
      'react-dom': reactDomDir,
    },
    dedupe: ['react', 'react-dom'],
  },
  server: {
    host: '127.0.0.1',
    port: Number(process.env.VITE_PORT) || 5173,
    strictPort: true,
    // §4.2 dev 注入完整 CSP(含 frame-ancestors,meta 不支持);
    // 生产由 gateway / 反代在响应头注入。
    headers: {
      'Content-Security-Policy': [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com data:",
        "img-src 'self' data: https:",
        "connect-src 'self' ws: wss: http://127.0.0.1:8000",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
      ].join('; '),
    },
    proxy: {
      // /health 不在 /api 前缀下,单独代理(服务徽章条与状态页依赖)
      '/api': { target: BACKEND, changeOrigin: true },
      '/health': { target: BACKEND, changeOrigin: true },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './tests/setup.ts',
    include: ['tests/unit/**/*.test.{ts,tsx}'],
  },
});
