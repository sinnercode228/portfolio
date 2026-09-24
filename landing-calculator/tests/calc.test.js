'use strict';
/* Тесты чистых функций калькулятора: node --test */
const test = require('node:test');
const assert = require('node:assert/strict');

const cfg = require('../js/config.js');
const Calc = require('../js/calc.js');

const NB = '\u00A0';
const sum = (items) => items.reduce((s, i) => s + i.amount, 0);

test('значения по умолчанию: газобетон 120 м², 1 этаж, white box, плита', () => {
  const r = Calc.calculate({}, cfg);
  assert.deepEqual(r.input, {
    area: 120, floors: 1, tech: 'aerated', finish: 'whitebox', slab: true, terrace: 0, garage: false
  });
  // коробка: 120 × 31 000 = 3 720 000
  // отделка: 3 720 000 × 0,3 = 1 116 000
  // плита: ceil(120 × 1,1) = 132 м² × 7 500 = 990 000
  assert.deepEqual(r.items.map((i) => [i.id, i.amount]), [
    ['shell', 3720000],
    ['finish', 1116000],
    ['slab', 990000]
  ]);
  assert.equal(r.total, 5826000);
  assert.equal(r.perM2, 48600);
  assert.equal(r.months, 7); // ceil(5 + 1,5 + 0,2)
});

test('двухэтажный дом дешевле за м² коробки и с меньшей плитой', () => {
  const one = Calc.calculate({ area: 160, floors: 1, finish: 'shell' }, cfg);
  const two = Calc.calculate({ area: 160, floors: 2, finish: 'shell' }, cfg);
  const shell = (r) => r.items.find((i) => i.id === 'shell').amount;
  const slab = (r) => r.items.find((i) => i.id === 'slab').amount;
  // 31 000 × 0,94 = 29 140 ₽/м² → 160 × 29 140 = 4 662 400 → 4 662 000
  assert.equal(shell(two), 4662000);
  assert.ok(shell(two) < shell(one));
  // пятно дома 80 м² → ceil(88) × 7 500 = 660 000
  assert.equal(slab(two), 660000);
  assert.equal(two.footprint, 80);
});

test('коробка без опций: только одна строка в разбивке', () => {
  const r = Calc.calculate({ area: 100, tech: 'frame', finish: 'shell', slab: false, terrace: 0, garage: false }, cfg);
  assert.deepEqual(r.items.map((i) => i.id), ['shell']);
  assert.equal(r.total, 2400000);
  assert.equal(r.perM2, 24000);
  assert.equal(r.months, 3);
});

test('все опции: терраса, гараж, плита, «под ключ»', () => {
  const r = Calc.calculate({
    area: 200, floors: 2, tech: 'brick', finish: 'turnkey', slab: true, terrace: 30, garage: true
  }, cfg);
  const byId = Object.fromEntries(r.items.map((i) => [i.id, i.amount]));
  assert.equal(byId.shell, 8084000); // 200 × 40 420
  assert.equal(byId.finish, 5255000); // 8 084 000 × 0,65 = 5 254 600 → 5 255 000
  assert.equal(byId.slab, 825000); // ceil(100 × 1,1) = 110 × 7 500
  assert.equal(byId.terrace, 360000); // 30 × 12 000
  assert.equal(byId.garage, 950000);
  assert.equal(r.total, 15474000);
  assert.equal(r.months, 12); // 7 (кирпич) + 3 (под ключ) + 1 (200 м²) + 0,5 (2 этажа) + 0,5 (гараж)
});

test('сумма строк разбивки всегда равна итогу (перебор комбинаций)', () => {
  const areas = [40, 57, 120, 233, 400];
  for (const tech of Object.keys(cfg.technologies)) {
    for (const finish of Object.keys(cfg.finishes)) {
      for (const floors of [1, 2]) {
        for (const area of areas) {
          for (const flags of [[true, 0, true], [false, 17, false], [true, 80, false]]) {
            const [slab, terrace, garage] = flags;
            const r = Calc.calculate({ area, floors, tech, finish, slab, terrace, garage }, cfg);
            assert.equal(sum(r.items), r.total, JSON.stringify(r.input));
            assert.ok(r.items.every((i) => Number.isInteger(i.amount) && i.amount > 0));
            assert.ok(r.total % cfg.rounding === 0);
          }
        }
      }
    }
  }
});

test('стоимость растёт с площадью и уровнем отделки', () => {
  let prev = 0;
  for (let area = cfg.area.min; area <= cfg.area.max; area += 10) {
    const t = Calc.calculate({ area }, cfg).total;
    assert.ok(t >= prev, `area ${area}`);
    prev = t;
  }
  const [shell, whitebox, turnkey] = ['shell', 'whitebox', 'turnkey']
    .map((finish) => Calc.calculate({ finish }, cfg).total);
  assert.ok(shell < whitebox && whitebox < turnkey);
});

test('нормализация: площадь ограничивается и парсится из строк', () => {
  const n = (raw) => Calc.normalizeInput(raw, cfg);
  assert.equal(n({ area: 10 }).area, 40);
  assert.equal(n({ area: 9999 }).area, 400);
  assert.equal(n({ area: '150,6' }).area, 151);
  assert.equal(n({ area: '1 20' }).area, 120);
  assert.equal(n({ area: 'abc' }).area, 120);
  assert.equal(n({ area: '' }).area, 120);
  assert.equal(n({ area: null }).area, 120);
  assert.equal(n({ area: Infinity }).area, 120);
});

test('нормализация: неизвестные значения заменяются значениями по умолчанию', () => {
  const n = (raw) => Calc.normalizeInput(raw, cfg);
  assert.equal(n({ tech: 'стекло' }).tech, 'aerated');
  assert.equal(n({ tech: '__proto__' }).tech, 'aerated');
  assert.equal(n({ tech: 'constructor' }).tech, 'aerated');
  assert.equal(n({ finish: 'luxury' }).finish, 'whitebox');
  assert.equal(n({ floors: 3 }).floors, 1);
  assert.equal(n({ floors: '2' }).floors, 2);
  assert.equal(n(null).area, 120);
});

test('нормализация: терраса и флаги', () => {
  const n = (raw) => Calc.normalizeInput(raw, cfg);
  assert.equal(n({ terrace: 3 }).terrace, 6); // меньше минимума → минимум
  assert.equal(n({ terrace: 500 }).terrace, 80);
  assert.equal(n({ terrace: -5 }).terrace, 0);
  assert.equal(n({ terrace: '24' }).terrace, 24);
  assert.equal(n({ slab: '0' }).slab, false);
  assert.equal(n({ slab: '1' }).slab, true);
  assert.equal(n({ garage: 'on' }).garage, true);
  assert.equal(n({ garage: 'nope' }).garage, false);
  assert.equal(n({}).slab, true); // из defaults
});

test('срок строительства', () => {
  const m = (raw) => Calc.calculate(raw, cfg).months;
  assert.equal(m({ area: 80, tech: 'frame', finish: 'shell' }), 3);
  assert.equal(m({ area: 100, tech: 'timber', finish: 'turnkey' }), 7);
  assert.equal(m({ area: 300, floors: 2, tech: 'brick', finish: 'turnkey', garage: true }), 13); // 7+3+2+0,5+0,5
});

test('форматирование денег', () => {
  assert.equal(Calc.formatMoney(4350000), `4${NB}350${NB}000${NB}₽`);
  assert.equal(Calc.formatMoney(999), `999${NB}₽`);
  assert.equal(Calc.formatMoney(0), `0${NB}₽`);
  assert.equal(Calc.formatMoney(1234.6), `1${NB}235${NB}₽`);
  assert.equal(Calc.formatMoney(-1500), `−1${NB}500${NB}₽`);
  assert.equal(Calc.formatShortMoney(5826000), `5,83${NB}млн${NB}₽`);
  assert.equal(Calc.formatShortMoney(12000000), `12${NB}млн${NB}₽`);
  assert.equal(Calc.formatShortMoney(950000), `950${NB}тыс.${NB}₽`);
});

test('склонение', () => {
  const f = ['месяц', 'месяца', 'месяцев'];
  const cases = { 1: 'месяц', 2: 'месяца', 4: 'месяца', 5: 'месяцев', 11: 'месяцев', 12: 'месяцев', 14: 'месяцев', 21: 'месяц', 22: 'месяца', 25: 'месяцев', 101: 'месяц', 111: 'месяцев' };
  for (const [n, word] of Object.entries(cases)) assert.equal(Calc.pluralize(Number(n), f), word, n);
  assert.equal(Calc.formatMonths(7), `7${NB}месяцев`);
});

test('состояние в URL: кодирование и обратное чтение', () => {
  const input = { area: 148, floors: 2, tech: 'timber', finish: 'turnkey', slab: false, terrace: 24, garage: true };
  const qs = Calc.encodeState(input);
  assert.equal(qs, 'area=148&floors=2&tech=timber&finish=turnkey&slab=0&terrace=24&garage=1');
  assert.deepEqual(Calc.decodeState('?' + qs, cfg), input);
  assert.equal(Calc.decodeState('', cfg), null);
  assert.equal(Calc.decodeState('?utm_source=ya', cfg), null);
  const partial = Calc.decodeState('?tech=brick&area=9999', cfg);
  assert.equal(partial.tech, 'brick');
  assert.equal(partial.area, 400);
  assert.equal(partial.finish, cfg.defaults.finish);
});

test('текстовое резюме для заявки', () => {
  const r = Calc.calculate({ area: 96, tech: 'timber', finish: 'turnkey', terrace: 18 }, cfg);
  const text = Calc.formatCalcSummary(r, cfg);
  assert.ok(!text.includes(NB), 'без неразрывных пробелов — удобно для мессенджеров');
  assert.match(text, /^Технология стен: Брус$/m);
  assert.match(text, /^Площадь: 96 м², 1 этаж$/m);
  assert.match(text, /^Отделка: Под ключ$/m);
  assert.match(text, /^Терраса: 18 м²$/m);
  assert.match(text, /^Гараж: нет$/m);
  assert.match(text, /^Итого: ≈ [\d ]+ ₽ \([\d ]+ ₽\/м²\)$/m);
  assert.equal(text.split('\n').length, 8);
});
