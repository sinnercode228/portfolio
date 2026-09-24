/* Тесты примера serverless-функции (Telegram / e-mail) с подменённым fetch: node --test */
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import worker, { handleLead, formatLeadMessage, escapeHtml, displayPhone } from '../serverless/telegram-lead.mjs';

const require = createRequire(import.meta.url);
const cfg = require('../js/config.js');
const Calc = require('../js/calc.js');
const F = require('../js/form-utils.js');

const ENV = { TELEGRAM_BOT_TOKEN: '123:TEST', TELEGRAM_CHAT_ID: '-100500', ALLOWED_ORIGIN: 'https://sinnercode228.github.io' };

function makeLead(overrides = {}) {
  const result = Calc.calculate({ area: 120, tech: 'aerated', finish: 'whitebox', terrace: 20 }, cfg);
  return {
    ...F.buildLeadPayload(
      { name: 'Анна', phone: '+7 (912) 345-67-89', comment: 'Перезвоните после 18:00', website: '' },
      { result, summary: Calc.formatCalcSummary(result, cfg) },
      { page: 'https://example.com/', utm: { utm_source: 'ya' } }
    ),
    ...overrides
  };
}

const post = (body) => new Request('https://lead.example.workers.dev/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: typeof body === 'string' ? body : JSON.stringify(body)
});

function mockFetch(status = 200) {
  const calls = [];
  const fn = async (url, init) => {
    calls.push({ url, init, body: JSON.parse(init.body) });
    return new Response(JSON.stringify({ ok: status < 400 }), { status });
  };
  fn.calls = calls;
  return fn;
}

test('OPTIONS — CORS preflight', async () => {
  const res = await handleLead(new Request('https://x/', { method: 'OPTIONS' }), ENV);
  assert.equal(res.status, 204);
  assert.equal(res.headers.get('Access-Control-Allow-Origin'), ENV.ALLOWED_ORIGIN);
});

test('GET → 405, битый JSON → 400', async () => {
  assert.equal((await handleLead(new Request('https://x/'), ENV)).status, 405);
  assert.equal((await handleLead(post('{oops'), ENV, mockFetch())).status, 400);
  assert.equal((await handleLead(post('null'), ENV, mockFetch())).status, 400);
});

test('слишком большой запрос → 413', async () => {
  const res = await handleLead(post(makeLead({ comment: 'x'.repeat(30000) })), ENV, mockFetch());
  assert.equal(res.status, 413);
});

test('невалидный телефон → 422 и ничего не отправляется', async () => {
  const f = mockFetch();
  const res = await handleLead(post(makeLead({ phone: '+7912' })), ENV, f);
  assert.equal(res.status, 422);
  assert.ok((await res.json()).errors.phone);
  assert.equal(f.calls.length, 0);
});

test('honeypot: бот получает 200, но в Telegram ничего не уходит', async () => {
  const f = mockFetch();
  const res = await handleLead(post(makeLead({ website: 'http://spam' })), ENV, f);
  assert.equal(res.status, 200);
  assert.equal(f.calls.length, 0);
});

test('нет ни одного канала доставки → 500', async () => {
  const res = await handleLead(post(makeLead()), {}, mockFetch());
  assert.equal(res.status, 500);
});

test('успешная заявка уходит в Telegram с расчётом', async () => {
  const f = mockFetch();
  const res = await handleLead(post(makeLead()), ENV, f);
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { ok: true });
  assert.equal(f.calls.length, 1);
  const [call] = f.calls;
  assert.equal(call.url, 'https://api.telegram.org/bot123:TEST/sendMessage');
  assert.equal(call.body.chat_id, '-100500');
  assert.equal(call.body.parse_mode, 'HTML');
  assert.match(call.body.text, /<b>Имя:<\/b> Анна/);
  assert.match(call.body.text, /\+7 \(912\) 345-67-89/);
  assert.match(call.body.text, /<pre>Технология стен: Газобетон/);
  assert.match(call.body.text, /Терраса: 20 м²/);
  assert.match(call.body.text, /utm_source=ya/);
});

test('HTML в полях экранируется', async () => {
  const text = formatLeadMessage(makeLead({ name: '<b>Хакер</b>', comment: 'a & b < c' }));
  assert.match(text, /&lt;b&gt;Хакер&lt;\/b&gt;/);
  assert.match(text, /a &amp; b &lt; c/);
  assert.equal(escapeHtml('"'), '&quot;');
});

test('телефон в сообщении берётся из проверенного поля, а не из phoneFormatted', () => {
  const text = formatLeadMessage(makeLead({ phoneFormatted: 'позвоните на +7 999 000-00-00' }));
  assert.match(text, /<b>Телефон:<\/b> \+7 \(912\) 345-67-89/);
  assert.doesNotMatch(text, /999/);
  assert.equal(displayPhone({ phone: '+79123456789' }), '+7 (912) 345-67-89');
});

test('длинные поля обрезаются, сообщение укладывается в лимит Telegram', () => {
  const text = formatLeadMessage(makeLead({ comment: 'я'.repeat(5000), meta: { page: 'https://x/?' + 'q'.repeat(5000) } }));
  const visible = text.replace(/<[^>]+>/g, '');
  assert.ok(visible.length <= 4096, `length ${visible.length}`);
});

test('ошибка Telegram → 502', async (t) => {
  const logged = [];
  t.mock.method(console, 'error', (err) => logged.push(String(err))); // не шумим в выводе тестов
  const res = await handleLead(post(makeLead()), ENV, mockFetch(500));
  assert.equal(res.status, 502);
  assert.match(logged[0], /Telegram API: HTTP 500/);
});

test('Telegram + e-mail через Resend: оба канала вызываются', async () => {
  const f = mockFetch();
  const env = { ...ENV, RESEND_API_KEY: 're_test', LEAD_EMAIL_TO: 'sales@example.com' };
  const res = await handleLead(post(makeLead()), env, f);
  assert.equal(res.status, 200);
  const urls = f.calls.map((c) => c.url).sort();
  assert.deepEqual(urls, ['https://api.resend.com/emails', 'https://api.telegram.org/bot123:TEST/sendMessage']);
  const mail = f.calls.find((c) => c.url.includes('resend')).body;
  assert.deepEqual(mail.to, ['sales@example.com']);
  assert.match(mail.subject, /Анна/);
});

test('экспорт по умолчанию совместим с Cloudflare Workers', () => {
  assert.equal(typeof worker.fetch, 'function');
});
