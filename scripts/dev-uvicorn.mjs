#!/usr/bin/env node
/**
 * 开发 uvicorn 启动包装器 —— 支持环境变量覆盖端口（uvicorn 本身不读 PORT 环境变量）。
 *
 * 用法（见根 package.json 的 dev:api / dev:agent）：
 *   node scripts/dev-uvicorn.mjs <app> <default-port> <app-dir> <PORT_ENV_VAR>
 *
 * 例：node scripts/dev-uvicorn.mjs api_backend.main:app 19878 services/api API_PORT
 *   - 未设置 API_PORT 时用 19878
 *   - 设置 API_PORT=19999 时监听 19999
 *
 * 端口被占用时透传 uvicorn 错误并附加排查提示（Windows/Linux 命令）。
 */
import { spawn } from 'node:child_process';
import process from 'node:process';

const [, , app = '', defaultPort = '8000', appDir = '', portEnvVar = ''] = process.argv;

if (!app || !defaultPort || !appDir || !portEnvVar) {
  console.error(
    '用法: node scripts/dev-uvicorn.mjs <app> <default-port> <app-dir> <PORT_ENV_VAR>'
  );
  process.exit(1);
}

const port = process.env[portEnvVar] || defaultPort;
const args = [
  '-m',
  'uvicorn',
  app,
  '--reload',
  '--host',
  '127.0.0.1',
  '--port',
  String(port),
  '--app-dir',
  appDir,
];

console.log(`[dev-uvicorn] ${portEnvVar}=${process.env[portEnvVar] ?? '(未设置)'} → 使用端口 ${port}`);
console.log(`[dev-uvicorn] uvicorn ${app} 127.0.0.1:${port} (app-dir: ${appDir})`);

const child = spawn('python', args, { stdio: 'inherit' });

child.on('error', (err) => {
  if (err.code === 'ENOENT') {
    console.error('[dev-uvicorn] 未找到 python 可执行文件，请先安装 Python 3.11+');
  } else {
    console.error(`[dev-uvicorn] 启动失败: ${err.message}`);
  }
  process.exit(1);
});

child.on('exit', (code, signal) => {
  // 仅非信号终止且非零退出（uvicorn 端口占用 WinError 10048 / Errno 98）时提示排查
  if (signal === null && code !== 0) {
    console.error('');
    console.error(`端口 ${port} 可能被占用，排查命令:`);
    console.error('  Windows: netstat -ano | findstr ' + port);
    console.error('  Linux/Mac: lsof -i :' + port);
  }
  process.exit(signal === null ? (code ?? 0) : 130);
});
