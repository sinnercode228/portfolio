/**
 * Пример serverless-функции для приёма заявок с лендинга.
 * Заявка (JSON из js/app.js) → сообщение в Telegram и/или письмо на e-mail.
 *
 * Написано на стандартном Web Fetch API (Request → Response), поэтому:
 *   • Cloudflare Workers — работает как есть (export default { fetch }).
 *   • Vercel / Netlify    — нужна обёртка в 3 строки, см. README → «Подключение заявок».
 *
 * Переменные окружения (секреты):
 *   TELEGRAM_BOT_TOKEN  — токен бота от @BotFather
 *   TELEGRAM_CHAT_ID    — id чата/группы, куда слать заявки
 *   ALLOWED_ORIGIN      — адрес сайта, например https://username.github.io ('*' по умолчанию)
 *   RESEND_API_KEY      — (необязательно) ключ Resend для писем
 *   LEAD_EMAIL_TO       — (необязательно) куда слать письмо
 *   LEAD_EMAIL_FROM     — (необязательно) от кого, домен должен быть подтверждён в Resend
 */

const MAX_BODY = 20_000; // символов — заявке больше не нужно

function corsHeaders(env) {
  return {
    'Access-Control-Allow-Origin': env.ALLOWED_ORIGIN || '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
    Vary: 'Origin'
  };
}

function json(data, status, env) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', ...corsHeaders(env) }
  });
}

export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
}

/** Проверяет заявку. Возвращает объект ошибок (пустой — всё хорошо). */
export function validateLead(lead) {
  const errors = {};
  const name = String(lead?.name ?? '').trim();
  const phone = String(lead?.phone ?? '').replace(/[^\d+]/g, '');
  if (name.length < 2 || name.length > 80) errors.name = 'name: 2–80 символов';
  if (!/^\+7\d{10}$/.test(phone)) errors.phone = 'phone: формат +7XXXXXXXXXX';
  if (String(lead?.comment ?? '').length > 1000) errors.comment = 'comment: до 1000 символов';
  return errors;
}

const clip = (value, max) => {
  const s = String(value ?? '');
  return s.length > max ? s.slice(0, max - 1) + '…' : s;
};

/**
 * Текст сообщения для Telegram (parse_mode: HTML).
 * Поля обрезаются заранее, чтобы уложиться в лимит 4096 символов
 * (Telegram считает длину уже после разбора HTML-сущностей).
 */
export function formatLeadMessage(lead) {
  const lines = [
    '<b>Новая заявка с сайта</b>',
    '',
    `<b>Имя:</b> ${escapeHtml(clip(lead.name, 80))}`,
    `<b>Телефон:</b> ${escapeHtml(clip(lead.phoneFormatted || lead.phone, 30))}`
  ];
  if (lead.comment) lines.push(`<b>Комментарий:</b> ${escapeHtml(clip(lead.comment, 1000))}`);
  if (lead.calculation?.summary) {
    lines.push('', '<b>Расчёт из калькулятора</b>', `<pre>${escapeHtml(clip(lead.calculation.summary, 1500))}</pre>`);
  } else {
    lines.push('', '<i>Расчёт не приложен</i>');
  }
  const utm = lead.meta?.utm && typeof lead.meta.utm === 'object'
    ? Object.entries(lead.meta.utm).map(([k, v]) => `${k}=${v}`).join(', ')
    : '';
  if (utm) lines.push(`<b>UTM:</b> ${escapeHtml(clip(utm, 300))}`);
  if (lead.meta?.page) lines.push(`<b>Страница:</b> ${escapeHtml(clip(lead.meta.page, 300))}`);
  return lines.join('\n');
}

async function sendTelegram(lead, env, fetchImpl) {
  const res = await fetchImpl(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      chat_id: env.TELEGRAM_CHAT_ID,
      text: formatLeadMessage(lead),
      parse_mode: 'HTML',
      disable_web_page_preview: true
    })
  });
  if (!res.ok) throw new Error(`Telegram API: HTTP ${res.status}`);
}

async function sendEmail(lead, env, fetchImpl) {
  const res = await fetchImpl('https://api.resend.com/emails', {
    method: 'POST',
    headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      from: env.LEAD_EMAIL_FROM || 'Заявки <leads@example.com>',
      to: [env.LEAD_EMAIL_TO],
      subject: `Заявка: ${lead.name}, ${lead.phoneFormatted || lead.phone}`,
      html: formatLeadMessage(lead).replace(/\n/g, '<br>')
    })
  });
  if (!res.ok) throw new Error(`Resend API: HTTP ${res.status}`);
}

/**
 * Обработчик запроса.
 * @param {Request} request
 * @param {Record<string,string>} env — переменные окружения
 * @param {typeof fetch} [fetchImpl] — подменяется в тестах
 */
export async function handleLead(request, env = {}, fetchImpl = fetch) {
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: corsHeaders(env) });
  if (request.method !== 'POST') return json({ ok: false, error: 'Method not allowed' }, 405, env);

  const raw = await request.text();
  if (raw.length > MAX_BODY) return json({ ok: false, error: 'Payload too large' }, 413, env);

  let lead;
  try {
    lead = JSON.parse(raw);
  } catch {
    return json({ ok: false, error: 'Invalid JSON' }, 400, env);
  }
  if (!lead || typeof lead !== 'object') return json({ ok: false, error: 'Invalid JSON' }, 400, env);

  // Honeypot: люди это поле не видят. Боту отвечаем «ок», но ничего не отправляем.
  if (lead.website) return json({ ok: true }, 200, env);

  const errors = validateLead(lead);
  if (Object.keys(errors).length) return json({ ok: false, errors }, 422, env);

  const tasks = [];
  if (env.TELEGRAM_BOT_TOKEN && env.TELEGRAM_CHAT_ID) tasks.push(sendTelegram(lead, env, fetchImpl));
  if (env.RESEND_API_KEY && env.LEAD_EMAIL_TO) tasks.push(sendEmail(lead, env, fetchImpl));
  if (!tasks.length) return json({ ok: false, error: 'No delivery channel configured' }, 500, env);

  const results = await Promise.allSettled(tasks);
  const delivered = results.filter((r) => r.status === 'fulfilled').length;
  results.forEach((r) => { if (r.status === 'rejected') console.error(r.reason); });
  if (!delivered) return json({ ok: false, error: 'Delivery failed' }, 502, env);

  return json({ ok: true }, 200, env);
}

// Cloudflare Workers
export default {
  fetch(request, env) {
    return handleLead(request, env);
  }
};
