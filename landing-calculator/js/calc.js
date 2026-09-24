/*!
 * calc.js — чистые функции калькулятора стоимости дома (без DOM).
 * Браузер: window.HouseCalc. Node: const HouseCalc = require('./js/calc.js').
 */
(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.HouseCalc = api;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var NBSP = '\u00A0';
  var hasOwn = function (obj, key) {
    return key !== undefined && key !== null && Object.prototype.hasOwnProperty.call(obj, key);
  };

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  /** Число из строки/числа; «1 200,5» → 1200.5. Если не получилось — fallback. */
  function toNumber(value, fallback) {
    if (typeof value === 'string') value = value.replace(/[\s\u00A0]+/g, '').replace(',', '.');
    var n = typeof value === 'number' ? value : parseFloat(value);
    return Number.isFinite(n) ? n : fallback;
  }

  function toBool(value) {
    return value === true || value === 1 || value === '1' || value === 'true' || value === 'on' || value === 'yes';
  }

  function roundTo(value, step) {
    return step ? Math.round(value / step) * step : Math.round(value);
  }

  /** Приводит «сырые» значения формы/URL к корректному состоянию калькулятора. */
  function normalizeInput(raw, cfg) {
    raw = raw || {};
    var d = cfg.defaults;
    var step = cfg.area.step || 1;

    var area = toNumber(raw.area, d.area);
    area = clamp(Math.round(area / step) * step, cfg.area.min, cfg.area.max);

    var t = cfg.options.terrace;
    var terrace = Math.round(clamp(toNumber(raw.terrace, 0), 0, t.max));
    if (terrace > 0 && terrace < t.min) terrace = t.min;

    return {
      area: area,
      floors: Number(hasOwn(cfg.floors, raw.floors) ? raw.floors : d.floors),
      tech: hasOwn(cfg.technologies, raw.tech) ? String(raw.tech) : d.tech,
      finish: hasOwn(cfg.finishes, raw.finish) ? String(raw.finish) : d.finish,
      slab: raw.slab === undefined ? Boolean(d.slab) : toBool(raw.slab),
      terrace: terrace,
      garage: raw.garage === undefined ? Boolean(d.garage) : toBool(raw.garage)
    };
  }

  /** Ориентировочный срок строительства, целых месяцев. */
  function estimateMonths(input, cfg) {
    var m = cfg.technologies[input.tech].months + cfg.finishes[input.finish].months;
    m += Math.max(0, input.area - 100) / 100; // +1 мес. на каждые 100 м² сверх 100
    if (input.floors === 2) m += 0.5;
    if (input.garage) m += 0.5;
    return Math.max(1, Math.ceil(m - 1e-9));
  }

  /**
   * Основной расчёт.
   * @returns {{input, items: Array<{id,label,detail,amount}>, total, perM2, footprint, months}}
   */
  function calculate(rawInput, cfg) {
    var input = normalizeInput(rawInput, cfg);
    var tech = cfg.technologies[input.tech];
    var finish = cfg.finishes[input.finish];
    var floor = cfg.floors[input.floors];
    var opts = cfg.options;
    var r = cfg.rounding || 1;
    var items = [];

    var pricePerM2 = roundTo(tech.price * floor.coef, 10);
    var shell = roundTo(input.area * pricePerM2, r);
    items.push({
      id: 'shell',
      label: 'Коробка: ' + tech.label.toLowerCase(),
      detail: input.area + NBSP + 'м² × ' + formatMoney(pricePerM2, cfg.currency) + '/м²',
      amount: shell
    });

    var finishCost = roundTo(shell * (finish.multiplier - 1), r);
    if (finishCost > 0) {
      items.push({
        id: 'finish',
        label: 'Отделка «' + finish.label + '»',
        detail: '+' + Math.round((finish.multiplier - 1) * 100) + '% к коробке',
        amount: finishCost
      });
    }

    var footprint = input.area / input.floors;
    if (input.slab) {
      var slabArea = Math.ceil(footprint * (1 + opts.slab.overhang) - 1e-9);
      items.push({
        id: 'slab',
        label: opts.slab.label,
        detail: slabArea + NBSP + 'м²',
        amount: roundTo(slabArea * opts.slab.pricePerM2, r)
      });
    }

    if (input.terrace > 0) {
      items.push({
        id: 'terrace',
        label: opts.terrace.label,
        detail: input.terrace + NBSP + 'м²',
        amount: roundTo(input.terrace * opts.terrace.pricePerM2, r)
      });
    }

    if (input.garage) {
      items.push({ id: 'garage', label: opts.garage.label, detail: '', amount: opts.garage.price });
    }

    var total = items.reduce(function (sum, item) { return sum + item.amount; }, 0);

    return {
      input: input,
      items: items,
      total: total,
      perM2: roundTo(total / input.area, 100),
      footprint: Math.round(footprint * 10) / 10,
      months: estimateMonths(input, cfg)
    };
  }

  /* ---------- Форматирование ---------- */

  /** 4350000 → «4 350 000» (неразрывные пробелы) */
  function groupDigits(n) {
    var v = Math.round(n);
    var s = String(Math.abs(v)).replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
    return (v < 0 ? '−' : '') + s;
  }

  function formatMoney(n, currency) {
    return groupDigits(n) + NBSP + (currency || '₽');
  }

  /** 4350000 → «4,35 млн ₽»; меньше миллиона → «950 тыс. ₽» */
  function formatShortMoney(n, currency) {
    var cur = currency || '₽';
    if (Math.abs(n) >= 1e6) {
      var mln = Math.round(n / 1e4) / 100;
      return String(mln).replace('.', ',') + NBSP + 'млн' + NBSP + cur;
    }
    return groupDigits(Math.round(n / 1000)) + NBSP + 'тыс.' + NBSP + cur;
  }

  /** pluralize(5, ['месяц', 'месяца', 'месяцев']) → «месяцев» */
  function pluralize(n, forms) {
    var a = Math.abs(Math.trunc(n)) % 100;
    var b = a % 10;
    if (a > 10 && a < 20) return forms[2];
    if (b > 1 && b < 5) return forms[1];
    if (b === 1) return forms[0];
    return forms[2];
  }

  function formatMonths(n) {
    return n + NBSP + pluralize(n, ['месяц', 'месяца', 'месяцев']);
  }

  /** Текстовое резюме расчёта — уходит в заявку и в Telegram. */
  function formatCalcSummary(result, cfg) {
    var i = result.input;
    return [
      'Технология стен: ' + cfg.technologies[i.tech].label,
      'Площадь: ' + i.area + ' м², ' + cfg.floors[i.floors].label,
      'Отделка: ' + cfg.finishes[i.finish].label,
      'Фундамент-плита: ' + (i.slab ? 'да' : 'нет'),
      'Терраса: ' + (i.terrace > 0 ? i.terrace + ' м²' : 'нет'),
      'Гараж: ' + (i.garage ? 'да' : 'нет'),
      'Итого: ≈ ' + formatMoney(result.total, cfg.currency) + ' (' + formatMoney(result.perM2, cfg.currency) + '/м²)',
      'Срок строительства: ≈ ' + formatMonths(result.months)
    ].join('\n').replace(/\u00A0/g, ' ');
  }

  /* ---------- Состояние в URL (ссылка «поделиться расчётом») ---------- */

  var STATE_KEYS = ['area', 'floors', 'tech', 'finish', 'slab', 'terrace', 'garage'];

  function encodeState(input) {
    var p = new URLSearchParams();
    p.set('area', String(input.area));
    p.set('floors', String(input.floors));
    p.set('tech', input.tech);
    p.set('finish', input.finish);
    p.set('slab', input.slab ? '1' : '0');
    p.set('terrace', String(input.terrace));
    p.set('garage', input.garage ? '1' : '0');
    return p.toString();
  }

  /** Возвращает нормализованное состояние или null, если в строке нет параметров калькулятора. */
  function decodeState(search, cfg) {
    var p = new URLSearchParams(search || '');
    var raw = {};
    var found = false;
    STATE_KEYS.forEach(function (key) {
      if (p.has(key)) {
        raw[key] = p.get(key);
        found = true;
      }
    });
    return found ? normalizeInput(raw, cfg) : null;
  }

  return {
    clamp: clamp,
    toNumber: toNumber,
    roundTo: roundTo,
    normalizeInput: normalizeInput,
    estimateMonths: estimateMonths,
    calculate: calculate,
    groupDigits: groupDigits,
    formatMoney: formatMoney,
    formatShortMoney: formatShortMoney,
    pluralize: pluralize,
    formatMonths: formatMonths,
    formatCalcSummary: formatCalcSummary,
    encodeState: encodeState,
    decodeState: decodeState
  };
});
