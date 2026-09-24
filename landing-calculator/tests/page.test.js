'use strict';
/* Статические проверки страницы: ссылки, id, подписи полей, пресеты, размер. node --test */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
const appJs = fs.readFileSync(path.join(ROOT, 'js', 'app.js'), 'utf8');
const cfg = require('../js/config.js');

// Комментарии убираем, чтобы закомментированная Метрика не мешала проверкам
const markup = html.replace(/<!--[\s\S]*?-->/g, '');
const ids = [...markup.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]);
const idSet = new Set(ids);

test('id на странице уникальны', () => {
  const dupes = ids.filter((id, i) => ids.indexOf(id) !== i);
  assert.deepEqual(dupes, []);
});

test('локальные файлы из src/href существуют', () => {
  const refs = [...markup.matchAll(/\s(?:src|href)="([^"#][^"]*)"/g)]
    .map((m) => m[1])
    .filter((u) => !/^(https?:|mailto:|tel:|data:)/.test(u));
  assert.ok(refs.length >= 5);
  for (const ref of refs) assert.ok(fs.existsSync(path.join(ROOT, ref)), ref);
});

test('якорные ссылки и <use href> ведут на существующие id', () => {
  const anchors = [...markup.matchAll(/\shref="#([^"]+)"/g)].map((m) => m[1]);
  for (const id of anchors) assert.ok(idSet.has(id), '#' + id);
});

test('все id, которые ищет app.js, есть в разметке', () => {
  const wanted = new Set([
    ...[...appJs.matchAll(/\$\('#([\w-]+)'/g)].map((m) => m[1]),
    ...[...appJs.matchAll(/getElementById\('([\w-]+)'\)/g)].map((m) => m[1]),
    // ошибки полей формы ищутся как `${input.id}-error`
    ...['lead-name', 'lead-phone', 'lead-comment', 'lead-consent'].map((id) => id + '-error')
  ]);
  assert.ok(wanted.size > 20);
  for (const id of wanted) assert.ok(idSet.has(id), id);
});

test('у каждого поля ввода есть подпись', () => {
  const inputs = [...markup.matchAll(/<(input|textarea|select)\b[^>]*>/g)];
  for (const m of inputs) {
    const tag = m[0];
    if (/type="hidden"/.test(tag)) continue;
    const id = (tag.match(/\sid="([^"]+)"/) || [])[1];
    const before = markup.slice(0, m.index);
    const wrapped = before.lastIndexOf('<label') > before.lastIndexOf('</label>');
    const labelled = /aria-label(ledby)?="/.test(tag) || (id && markup.includes(`for="${id}"`));
    assert.ok(wrapped || labelled, tag);
  }
});

test('пресеты в data-preset — корректный JSON с известными значениями', () => {
  const presets = [...markup.matchAll(/data-preset='([^']+)'/g)].map((m) => JSON.parse(m[1]));
  assert.equal(presets.length, 10); // 4 технологии + 6 проектов
  for (const p of presets) {
    if (p.tech) assert.ok(cfg.technologies[p.tech], p.tech);
    if (p.finish) assert.ok(cfg.finishes[p.finish], p.finish);
    if (p.area) assert.ok(p.area >= cfg.area.min && p.area <= cfg.area.max);
  }
});

test('подписи карточек проектов совпадают с их пресетами (цена считается по пресету)', () => {
  const cards = [...markup.matchAll(/<li class="project" data-tech="([^"]+)"[\s\S]*?<\/li>/g)];
  assert.equal(cards.length, 6);
  const text = (s) => s.replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').toLowerCase();
  for (const [card, dataTech] of cards) {
    const tags = text(card.match(/<p class="project__tags">([\s\S]*?)<\/p>/)[1]);
    const preset = JSON.parse(card.match(/data-preset='([^']+)'/)[1]);
    const name = card.match(/<h3>([^<]+)<\/h3>/)[1];
    assert.equal(dataTech, preset.tech, name + ': data-tech');
    assert.ok(tags.includes(cfg.technologies[preset.tech].label.toLowerCase()), name + ': технология');
    assert.ok(tags.includes(preset.area + ' м²'), name + ': площадь');
    assert.ok(tags.includes(text(cfg.floors[preset.floors].label)), name + ': этажность');
    assert.ok(tags.includes(cfg.finishes[preset.finish].label.toLowerCase()), name + ': отделка');
    assert.equal(tags.includes('терраса'), preset.terrace > 0, name + ': терраса');
    assert.equal(tags.includes('гараж'), preset.garage === true, name + ': гараж');
  }
});

test('телефон в шапке, меню и контактах один и тот же', () => {
  const tels = new Set([...markup.matchAll(/href="tel:([^"]+)"/g)].map((m) => m[1]));
  assert.equal(tels.size, 1, [...tels].join(', '));
  assert.ok([...markup.matchAll(/href="tel:/g)].length >= 3);
});

test('фильтры проектов соответствуют технологиям из конфига', () => {
  const filters = [...markup.matchAll(/data-filter="([^"]+)"/g)].map((m) => m[1]).filter((f) => f !== 'all');
  assert.deepEqual(filters.sort(), Object.keys(cfg.technologies).sort());
  const cards = [...markup.matchAll(/class="project" data-tech="([^"]+)"/g)].map((m) => m[1]);
  for (const t of cards) assert.ok(cfg.technologies[t], t);
});

test('демо-пометка и заглушка Метрики на месте', () => {
  assert.match(html, /Демо-проект \/ Demo project/);
  assert.match(html, /<meta name="robots" content="noindex, nofollow">/);
  assert.match(html, /<!--[\s\S]*mc\.yandex\.ru\/metrika[\s\S]*-->/, 'счётчик Метрики только в комментарии');
  assert.doesNotMatch(markup, /mc\.yandex\.ru/, 'активного счётчика нет');
  assert.match(appJs, /\/\/\s*window\.ym\(METRIKA_ID, 'reachGoal'/);
});

test('размер страницы: HTML + CSS + JS меньше 50 КБ в gzip', () => {
  const zlib = require('node:zlib');
  const files = ['index.html', 'css/styles.css', 'js/config.js', 'js/calc.js', 'js/form-utils.js', 'js/app.js', 'assets/favicon.svg'];
  const gz = files.reduce((s, f) => s + zlib.gzipSync(fs.readFileSync(path.join(ROOT, f)), { level: 9 }).length, 0);
  assert.ok(gz < 50 * 1024, `${(gz / 1024).toFixed(1)} КБ в gzip`);
});
