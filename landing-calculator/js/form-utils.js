/*!
 * form-utils.js — маска телефона, валидация и сборка заявки (чистые функции, без DOM).
 * Браузер: window.FormUtils. Node: require('./js/form-utils.js').
 */
(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.FormUtils = api;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var PHONE_LENGTH = 11; // 7 + 10 цифр

  function onlyDigits(value) {
    return String(value == null ? '' : value).replace(/\D/g, '');
  }

  /** Цифры российского номера: «8 (912) 345-67-89» → «79123456789». Максимум 11 цифр. */
  function extractPhoneDigits(value) {
    var d = onlyDigits(value);
    if (!d) return '';
    if (d[0] === '8') d = '7' + d.slice(1);
    else if (d[0] !== '7') d = '7' + d;
    return d.slice(0, PHONE_LENGTH);
  }

  /** Маска «+7 (912) 345-67-89», работает и для частично введённого номера. */
  function formatPhone(value) {
    var d = extractPhoneDigits(value);
    if (!d) return '';
    var out = '+7';
    var a = d.slice(1, 4);
    var b = d.slice(4, 7);
    var c = d.slice(7, 9);
    var e = d.slice(9, 11);
    if (a) out += ' (' + a;
    if (b) out += ') ' + b;
    if (c) out += '-' + c;
    if (e) out += '-' + e;
    return out;
  }

  function isPhoneComplete(value) {
    return extractPhoneDigits(value).length === PHONE_LENGTH;
  }

  /** «+7 (912) 345-67-89» → «+79123456789» (или '' для неполного номера) */
  function toE164(value) {
    return isPhoneComplete(value) ? '+' + extractPhoneDigits(value) : '';
  }

  /** Позиция курсора сразу после n-й цифры строки. */
  function caretAfterDigits(str, n) {
    if (n <= 0) return 0;
    var count = 0;
    for (var i = 0; i < str.length; i++) {
      if (/\d/.test(str[i])) {
        count++;
        if (count === n) return i + 1;
      }
    }
    return str.length;
  }

  /**
   * Переформатирует значение поля и пересчитывает позицию курсора,
   * чтобы при правке в середине номера курсор не «прыгал» в конец.
   */
  function reformatPhone(value, caret) {
    var str = String(value == null ? '' : value);
    if (caret == null || caret > str.length) caret = str.length;
    var raw = onlyDigits(str);
    var digits = extractPhoneDigits(str);
    var before = onlyDigits(str.slice(0, caret)).length;
    if (digits && raw[0] !== '7' && raw[0] !== '8') before += 1; // добавили код страны
    before = Math.min(before, digits.length);
    var formatted = formatPhone(digits);
    return { value: formatted, caret: caretAfterDigits(formatted, before) };
  }

  /**
   * Backspace, когда перед курсором символ маски (скобка, пробел, дефис):
   * удаляем ближайшую цифру слева. Возвращает null, если подходит обычное поведение.
   */
  function phoneBackspace(value, caret) {
    var str = String(value == null ? '' : value);
    if (!caret || /\d/.test(str[caret - 1])) return null;
    var i = caret - 1;
    while (i >= 0 && !/\d/.test(str[i])) i--;
    if (i < 0) return null;
    return reformatPhone(str.slice(0, i) + str.slice(caret), i);
  }

  /* ---------- Валидация ---------- */

  var LIMITS = { nameMin: 2, nameMax: 80, commentMax: 1000 };

  /**
   * @param {{name, phone, comment, consent}} fields
   * @returns {{valid: boolean, errors: Object<string,string>}}
   */
  function validateLead(fields) {
    var errors = {};
    var name = String(fields.name || '').trim();
    var phone = String(fields.phone || '').trim();
    var comment = String(fields.comment || '');

    if (name.length < LIMITS.nameMin) errors.name = 'Укажите имя — хотя бы 2 буквы.';
    else if (name.length > LIMITS.nameMax) errors.name = 'Имя слишком длинное — до 80 символов.';
    else if (!/\p{L}/u.test(name)) errors.name = 'Имя должно содержать буквы.';

    if (!phone) errors.phone = 'Укажите телефон — мы перезвоним с точной сметой.';
    else if (!isPhoneComplete(phone)) errors.phone = 'Номер неполный: нужно 10 цифр после +7.';

    if (comment.length > LIMITS.commentMax) errors.comment = 'Комментарий слишком длинный — до 1000 символов.';

    if (!fields.consent) errors.consent = 'Без согласия на обработку данных мы не сможем связаться с вами.';

    return { valid: Object.keys(errors).length === 0, errors: errors };
  }

  /** UTM-метки из query-строки */
  function parseUtm(search) {
    var p = new URLSearchParams(search || '');
    var utm = {};
    ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'].forEach(function (key) {
      var v = p.get(key);
      if (v) utm[key] = v.slice(0, 200);
    });
    return utm;
  }

  /**
   * Итоговый JSON заявки: контакты + расчёт калькулятора + служебные данные.
   * @param fields  {name, phone, comment, website}
   * @param calc    {result, summary} | null — результат HouseCalc.calculate и текстовое резюме
   * @param meta    {page, submittedAt, utm}
   */
  function buildLeadPayload(fields, calc, meta) {
    meta = meta || {};
    return {
      name: String(fields.name || '').trim(),
      phone: toE164(fields.phone),
      phoneFormatted: formatPhone(fields.phone),
      comment: String(fields.comment || '').trim(),
      website: String(fields.website || ''), // honeypot: у людей всегда пусто
      calculation: calc && calc.result ? {
        summary: calc.summary || '',
        total: calc.result.total,
        perM2: calc.result.perM2,
        months: calc.result.months,
        input: calc.result.input,
        items: calc.result.items.map(function (item) {
          return { label: item.label, detail: item.detail, amount: item.amount };
        })
      } : null,
      meta: {
        source: 'landing-calculator-demo',
        page: meta.page || '',
        submittedAt: meta.submittedAt || new Date().toISOString(),
        utm: meta.utm || {}
      }
    };
  }

  return {
    LIMITS: LIMITS,
    extractPhoneDigits: extractPhoneDigits,
    formatPhone: formatPhone,
    isPhoneComplete: isPhoneComplete,
    toE164: toE164,
    caretAfterDigits: caretAfterDigits,
    reformatPhone: reformatPhone,
    phoneBackspace: phoneBackspace,
    validateLead: validateLead,
    parseUtm: parseUtm,
    buildLeadPayload: buildLeadPayload
  };
});
