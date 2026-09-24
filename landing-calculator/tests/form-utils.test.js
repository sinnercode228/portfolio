'use strict';
/* Тесты маски телефона, валидации и сборки заявки: node --test */
const test = require('node:test');
const assert = require('node:assert/strict');

const cfg = require('../js/config.js');
const Calc = require('../js/calc.js');
const F = require('../js/form-utils.js');

test('цифры телефона: 8 → 7, добавление кода страны, обрезка до 11', () => {
  assert.equal(F.extractPhoneDigits('8 (912) 345-67-89'), '79123456789');
  assert.equal(F.extractPhoneDigits('+7 912 345 67 89'), '79123456789');
  assert.equal(F.extractPhoneDigits('9123456789'), '79123456789');
  assert.equal(F.extractPhoneDigits('+7 (912) 345-67-89 доб. 12'), '79123456789');
  assert.equal(F.extractPhoneDigits('abc'), '');
  assert.equal(F.extractPhoneDigits(null), '');
});

test('маска для частично введённого номера', () => {
  const cases = {
    '': '',
    '7': '+7',
    '8': '+7',
    '9': '+7 (9',
    '7912': '+7 (912',
    '79123': '+7 (912) 3',
    '7912345': '+7 (912) 345',
    '79123456': '+7 (912) 345-6',
    '791234567': '+7 (912) 345-67',
    '7912345678': '+7 (912) 345-67-8',
    '79123456789': '+7 (912) 345-67-89'
  };
  for (const [input, expected] of Object.entries(cases)) assert.equal(F.formatPhone(input), expected, input);
});

test('полнота номера и E.164', () => {
  assert.equal(F.isPhoneComplete('+7 (912) 345-67-89'), true);
  assert.equal(F.isPhoneComplete('+7 (912) 345-67'), false);
  assert.equal(F.toE164('8 912 345 67 89'), '+79123456789');
  assert.equal(F.toE164('+7 (912'), '');
});

test('курсор: ввод первой цифры и вставка в середину номера', () => {
  assert.deepEqual(F.reformatPhone('9', 1), { value: '+7 (9', caret: 5 });
  assert.deepEqual(F.reformatPhone('8', 1), { value: '+7', caret: 2 });
  // пользователь вписал «5» после «912» в «+7 (912) 3»
  assert.deepEqual(F.reformatPhone('+7 (9125) 3', 8), { value: '+7 (912) 53', caret: 10 });
  // ввод в конец
  assert.deepEqual(F.reformatPhone('+7 (912) 3456', 13), { value: '+7 (912) 345-6', caret: 14 });
  // вставка полного номера из буфера
  assert.deepEqual(F.reformatPhone('8 912 345 67 89', 15), { value: '+7 (912) 345-67-89', caret: 18 });
});

test('Backspace перепрыгивает символы маски', () => {
  // курсор перед «3» в «+7 (912) 345»: слева «) », удаляем «2»
  assert.deepEqual(F.phoneBackspace('+7 (912) 345', 9), { value: '+7 (913) 45', caret: 6 });
  // перед курсором цифра — работает обычное поведение браузера
  assert.equal(F.phoneBackspace('+7 (912) 345', 12), null);
  assert.equal(F.phoneBackspace('+7 (912', 0), null);
  // код страны удалить нельзя — он добавится обратно
  assert.deepEqual(F.phoneBackspace('+7 (912', 4), { value: '+7 (912', caret: 2 });
});

test('валидация заявки', () => {
  const ok = { name: 'Анна', phone: '+7 (912) 345-67-89', comment: '', consent: true };
  assert.deepEqual(F.validateLead(ok), { valid: true, errors: {} });

  const bad = F.validateLead({ name: ' ', phone: '+7 (912) 34', comment: 'x'.repeat(1001), consent: false });
  assert.equal(bad.valid, false);
  assert.deepEqual(Object.keys(bad.errors).sort(), ['comment', 'consent', 'name', 'phone']);

  assert.ok(F.validateLead({ ...ok, name: '12' }).errors.name, 'имя без букв');
  assert.ok(F.validateLead({ ...ok, name: 'Я'.repeat(81) }).errors.name, 'слишком длинное имя');
  assert.ok(F.validateLead({ ...ok, phone: '' }).errors.phone);
  assert.equal(F.validateLead({ ...ok, name: 'Jo' }).valid, true, 'латиница тоже подходит');
});

test('UTM-метки', () => {
  assert.deepEqual(F.parseUtm('?utm_source=ya&utm_campaign=dom&x=1'), { utm_source: 'ya', utm_campaign: 'dom' });
  assert.deepEqual(F.parseUtm(''), {});
  assert.equal(F.parseUtm('?utm_term=' + 'a'.repeat(500)).utm_term.length, 200);
});

test('payload заявки содержит контакты и расчёт', () => {
  const result = Calc.calculate({ area: 150, tech: 'frame', finish: 'turnkey', garage: true }, cfg);
  const summary = Calc.formatCalcSummary(result, cfg);
  const payload = F.buildLeadPayload(
    { name: '  Анна  ', phone: '8 912 345 67 89', comment: ' Участок 8 соток ', website: '' },
    { result, summary },
    { page: 'https://example.com/?utm_source=ya', submittedAt: '2026-01-01T00:00:00.000Z', utm: { utm_source: 'ya' } }
  );
  assert.equal(payload.name, 'Анна');
  assert.equal(payload.phone, '+79123456789');
  assert.equal(payload.phoneFormatted, '+7 (912) 345-67-89');
  assert.equal(payload.comment, 'Участок 8 соток');
  assert.equal(payload.website, '');
  assert.equal(payload.calculation.total, result.total);
  assert.equal(payload.calculation.summary, summary);
  assert.deepEqual(payload.calculation.input, result.input);
  assert.equal(payload.calculation.items.length, result.items.length);
  assert.deepEqual(payload.meta, {
    source: 'landing-calculator-demo',
    page: 'https://example.com/?utm_source=ya',
    submittedAt: '2026-01-01T00:00:00.000Z',
    utm: { utm_source: 'ya' }
  });
  // JSON-сериализуемо без потерь
  assert.deepEqual(JSON.parse(JSON.stringify(payload)), payload);
});

test('payload без расчёта, если галочка «приложить расчёт» снята', () => {
  const payload = F.buildLeadPayload({ name: 'Иван', phone: '+79123456789' }, null, {});
  assert.equal(payload.calculation, null);
  assert.match(payload.meta.submittedAt, /^\d{4}-\d{2}-\d{2}T/);
});
