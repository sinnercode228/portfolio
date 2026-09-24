/* Тесты локального сервера (npm start): типы файлов, 404/405, защита от выхода из папки. node --test */
import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { createServer, resolveFile, ROOT } from '../scripts/serve.mjs';

test('resolveFile: файлы внутри проекта и защита от ../', () => {
  assert.equal(resolveFile('/css/styles.css'), path.join(ROOT, 'css', 'styles.css'));
  assert.equal(resolveFile('/?area=120#calc'), ROOT);
  // «..» не выводит за пределы папки проекта
  for (const url of ['/../../etc/passwd', '/%2e%2e/%2e%2e/etc/passwd', '/js/..%5c..%5c..%5cetc%5cpasswd']) {
    const file = resolveFile(url);
    assert.ok(file === null || file === ROOT || file.startsWith(ROOT + path.sep), url + ' → ' + file);
  }
  // скрытые файлы и битые URL не раздаются
  assert.equal(resolveFile('/.gitignore'), null);
  assert.equal(resolveFile('/.venv/bin/python'), null);
  assert.equal(resolveFile('/%E0%A4%A'), null);
  assert.equal(resolveFile('/index.html%00.png'), null);
});

test('сервер отдаёт страницу, стили и скрипты с правильными типами', async (t) => {
  const server = createServer();
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  t.after(() => server.close());
  const base = `http://127.0.0.1:${server.address().port}`;

  const page = await fetch(base + '/?area=148&tech=brick');
  assert.equal(page.status, 200);
  assert.match(page.headers.get('content-type'), /^text\/html/);
  assert.match(await page.text(), /Демо-проект \/ Demo project/);

  for (const [url, type] of [['/css/styles.css', /^text\/css/], ['/js/app.js', /^text\/javascript/], ['/assets/favicon.svg', /^image\/svg\+xml/]]) {
    const res = await fetch(base + url);
    assert.equal(res.status, 200, url);
    assert.match(res.headers.get('content-type'), type, url);
    await res.arrayBuffer();
  }

  const missing = await fetch(base + '/nope.html');
  assert.equal(missing.status, 404);
  await missing.arrayBuffer();

  const hidden = await fetch(base + '/.gitignore');
  assert.equal(hidden.status, 404);
  await hidden.arrayBuffer();

  const post = await fetch(base + '/', { method: 'POST', body: '{}' });
  assert.equal(post.status, 405);
  await post.arrayBuffer();
});
