import '@testing-library/jest-dom/vitest';

// Vitest 中需使用 development 构建，否则 React Testing Library 的 act() 不可用
process.env.NODE_ENV = 'development';
