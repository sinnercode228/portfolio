#!/usr/bin/env node
/**
 * Мини-сервер для локального просмотра без зависимостей: `npm start` → http://localhost:8080
 * Работает одинаково на macOS, Linux и Windows (Python не нужен).
 * Другой порт: `npm start -- 3000` (или переменная окружения PORT).
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.md': 'text/plain; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8'
};

/** Путь из URL → файл внутри ROOT или null (защита от выхода из папки через ../). */
export function resolveFile(urlPath, root = ROOT) {
  let rel;
  try {
    rel = decodeURIComponent(new URL(urlPath, 'http://x').pathname);
  } catch {
    return null;
  }
  if (rel.includes('\0')) return null;
  const file = path.resolve(root, '.' + path.posix.normalize('/' + rel));
  if (file !== root && !file.startsWith(root + path.sep)) return null;
  // скрытые файлы и служебные папки не раздаём
  if (path.relative(root, file).split(path.sep).some((part) => part.startsWith('.') || part === 'node_modules')) return null;
  return file;
}

export function createServer(root = ROOT) {
  return http.createServer((req, res) => {
    if (req.method !== 'GET' && req.method !== 'HEAD') {
      res.writeHead(405, { Allow: 'GET, HEAD' }).end();
      return;
    }
    let file = resolveFile(req.url, root);
    if (file && fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
    if (!file || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }).end('404 — файл не найден');
      return;
    }
    res.writeHead(200, {
      'Content-Type': TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream',
      'Cache-Control': 'no-cache'
    });
    if (req.method === 'HEAD') res.end();
    else fs.createReadStream(file).pipe(res);
  });
}

// Запуск из командной строки (а не импорт в тестах)
const samePath = (a, b) => {
  try {
    const [x, y] = [fs.realpathSync(a), fs.realpathSync(b)];
    return process.platform === 'win32' ? x.toLowerCase() === y.toLowerCase() : x === y;
  } catch {
    return false;
  }
};
if (process.argv[1] && samePath(process.argv[1], fileURLToPath(import.meta.url))) {
  const port = Number(process.argv[2] || process.env.PORT || 8080);
  const server = createServer();
  server.on('error', (err) => {
    console.error(err.code === 'EADDRINUSE'
      ? `Порт ${port} занят. Запустите на другом: npm start -- 3000`
      : err.message);
    process.exit(1);
  });
  server.listen(port, () => {
    console.log(`«Полдень» (демо): http://localhost:${port}  — остановить: Ctrl+C`);
  });
}
