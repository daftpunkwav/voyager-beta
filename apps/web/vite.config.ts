import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { viteStaticCopy } from 'vite-plugin-static-copy';
import path from 'path';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);
const reactDir = path.dirname(require.resolve('react/package.json'));
const reactDomDir = path.dirname(require.resolve('react-dom/package.json'));
// pdf.js 中文 PDF 必需的字符映射与标准字体(阅读器按 /pdfjs/ 引用)
// glob 库不认 Windows 反斜杠:统一为 posix 分隔符
const pdfjsDir = path
  .dirname(require.resolve('pdfjs-dist/package.json'))
  .split(path.sep)
  .join('/');

const BACKEND = process.env.VITE_API_TARGET || 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [
    react(),
    viteStaticCopy({
      targets: [
        { src: `${pdfjsDir}/cmaps`, dest: 'pdfjs' },
        { src: `${pdfjsDir}/standard_fonts`, dest: 'pdfjs' },
      ],
    }),
  ],
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
