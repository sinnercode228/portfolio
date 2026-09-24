/*!
 * app.js — связывает страницу с чистыми функциями (config.js, calc.js, form-utils.js).
 */
(function () {
  'use strict';

  var cfg = window.HOUSE_CONFIG;
  var Calc = window.HouseCalc;
  var Form = window.FormUtils;
  if (!cfg || !Calc || !Form) {
    console.error('[Полдень] Не загружены config.js / calc.js / form-utils.js');
    return;
  }

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var esc = function (s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };

  /* =========================================================
     Яндекс.Метрика — цели (заглушка).
     Вставьте номер счётчика и раскомментируйте вызов ym() ниже.
     ========================================================= */
  var METRIKA_ID = null; // например: 12345678
  var firedGoals = {};
  function track(goal, params, onceOnly) {
    if (onceOnly) {
      if (firedGoals[goal]) return;
      firedGoals[goal] = true;
    }
    // if (METRIKA_ID && typeof window.ym === 'function') {
    //   window.ym(METRIKA_ID, 'reachGoal', goal, params);
    // }
    console.info('[Метрика · демо] reachGoal', goal, params || '', METRIKA_ID ? '' : '(счётчик не подключён)');
  }

  $$('[data-goal]').forEach(function (el) {
    el.addEventListener('click', function () { track(el.getAttribute('data-goal')); });
  });
  $$('a[href^="tel:"]').forEach(function (a) {
    a.addEventListener('click', function () { track('phone_click'); });
  });

  /* =========================================================
     Шапка и мобильное меню
     ========================================================= */
  var header = $('.site-header');
  var nav = $('#site-nav');
  var navToggle = $('#nav-toggle');
  var desktopMq = window.matchMedia('(min-width: 1080px)');

  function setNav(open) {
    if (open) nav.style.setProperty('--nav-top', Math.round(header.getBoundingClientRect().bottom) + 'px');
    navToggle.setAttribute('aria-expanded', String(open));
    navToggle.querySelector('.visually-hidden').textContent = open ? 'Закрыть меню' : 'Меню';
    nav.classList.toggle('is-open', open);
    document.body.classList.toggle('nav-open', open);
  }
  navToggle.addEventListener('click', function () {
    setNav(navToggle.getAttribute('aria-expanded') !== 'true');
  });
  nav.addEventListener('click', function (e) {
    if (e.target.closest('a')) setNav(false);
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && nav.classList.contains('is-open')) {
      setNav(false);
      navToggle.focus();
    }
  });
  var onDesktopChange = function () { if (desktopMq.matches) setNav(false); };
  if (desktopMq.addEventListener) desktopMq.addEventListener('change', onDesktopChange);

  var onScroll = function () { header.classList.toggle('is-scrolled', window.scrollY > 8); };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  /* =========================================================
     Цены из конфига в статичных блоках
     ========================================================= */
  $$('[data-tech-price]').forEach(function (el) {
    var t = cfg.technologies[el.getAttribute('data-tech-price')];
    if (t) el.textContent = 'от ' + Calc.formatMoney(t.price, cfg.currency) + '/м²';
  });
  $$('[data-tech-months]').forEach(function (el) {
    var t = cfg.technologies[el.getAttribute('data-tech-months')];
    if (t) el.textContent = '≈ ' + Calc.formatMonths(t.months);
  });
  var optPrice = {
    slab: Calc.formatMoney(cfg.options.slab.pricePerM2, cfg.currency) + '/м² пятна дома',
    terrace: Calc.formatMoney(cfg.options.terrace.pricePerM2, cfg.currency) + '/м²',
    garage: Calc.formatMoney(cfg.options.garage.price, cfg.currency)
  };
  $$('[data-opt-price]').forEach(function (el) {
    var key = el.getAttribute('data-opt-price');
    if (optPrice[key]) el.textContent = optPrice[key];
  });
  $$('[data-area-min]').forEach(function (el) { el.textContent = cfg.area.min; });
  $$('[data-area-max]').forEach(function (el) { el.textContent = cfg.area.max; });

  /* =========================================================
     Калькулятор
     ========================================================= */
  var form = $('#calc-form');
  var areaRange = $('#area-range');
  var areaNumber = $('#area-number');
  var techBox = $('#tech-options');
  var finishBox = $('#finish-options');
  var finishHint = $('#finish-hint');
  var slabBox = $('#opt-slab');
  var garageBox = $('#opt-garage');
  var terraceToggle = $('#terrace-toggle');
  var terraceArea = $('#terrace-area');
  var totalEl = $('#result-total');
  var perM2El = $('#result-per-m2');
  var monthsEl = $('#result-months');
  var barEl = $('#result-bar');
  var listEl = $('#result-list');
  var liveEl = $('#calc-live');
  var resultCard = $('#result-card');

  // Варианты технологий и отделки строятся из конфига
  techBox.innerHTML = Object.keys(cfg.technologies).map(function (key) {
    var t = cfg.technologies[key];
    return '<label class="choice">' +
      '<input type="radio" name="tech" value="' + esc(key) + '">' +
      '<span class="choice__body"><span class="choice__title">' + esc(t.label) + '</span>' +
      '<span class="choice__price">' + esc(Calc.formatMoney(t.price, cfg.currency)) + '/м²</span></span>' +
      '</label>';
  }).join('');

  finishBox.innerHTML = Object.keys(cfg.finishes).map(function (key) {
    return '<label class="seg"><input type="radio" name="finish" value="' + esc(key) + '" aria-describedby="finish-hint">' +
      '<span>' + esc(cfg.finishes[key].label) + '</span></label>';
  }).join('');

  [areaRange, areaNumber].forEach(function (el) {
    el.min = cfg.area.min;
    el.max = cfg.area.max;
    el.step = cfg.area.step;
  });
  terraceArea.min = cfg.options.terrace.min;
  terraceArea.max = cfg.options.terrace.max;

  function setRadio(name, value) {
    var input = form.querySelector('input[name="' + name + '"][value="' + value + '"]');
    if (input) input.checked = true;
  }

  function checkedValue(name) {
    var input = form.querySelector('input[name="' + name + '"]:checked');
    return input ? input.value : undefined;
  }

  function readForm() {
    return {
      area: areaNumber.value,
      floors: checkedValue('floors'),
      tech: checkedValue('tech'),
      finish: checkedValue('finish'),
      slab: slabBox.checked,
      // Терраса включена, а поле пустое или 0 — считаем минимальную площадь, а не «0 м²»
      terrace: terraceToggle.checked ? (Number(terraceArea.value) > 0 ? terraceArea.value : cfg.options.terrace.min) : 0,
      garage: garageBox.checked
    };
  }

  /** Записывает нормализованное состояние в контролы формы. */
  function applyState(raw) {
    var s = Calc.normalizeInput(raw, cfg);
    areaNumber.value = s.area;
    areaRange.value = s.area;
    setRadio('floors', s.floors);
    setRadio('tech', s.tech);
    setRadio('finish', s.finish);
    slabBox.checked = s.slab;
    garageBox.checked = s.garage;
    terraceToggle.checked = s.terrace > 0;
    terraceArea.disabled = !terraceToggle.checked;
    terraceArea.value = s.terrace > 0 ? s.terrace : cfg.options.terrace.suggested;
    update();
  }

  function updateRangeFill() {
    var min = Number(areaRange.min);
    var max = Number(areaRange.max);
    var pct = ((Number(areaRange.value) - min) / (max - min)) * 100;
    areaRange.style.setProperty('--fill', pct.toFixed(2) + '%');
    var area = Number(areaRange.value);
    areaRange.setAttribute('aria-valuetext', area + ' ' + Calc.pluralize(area, ['квадратный метр', 'квадратных метра', 'квадратных метров']));
  }

  // Плавная анимация итоговой суммы
  var shownTotal = 0;
  var rafId = 0;
  var finishTimer = 0;
  function setTotalNow(to) {
    cancelAnimationFrame(rafId);
    clearTimeout(finishTimer);
    shownTotal = to;
    totalEl.textContent = Calc.formatMoney(to, cfg.currency);
  }
  function renderTotal(to) {
    if (reduceMotion || !shownTotal || document.hidden) {
      setTotalNow(to);
      return;
    }
    cancelAnimationFrame(rafId);
    clearTimeout(finishTimer);
    var from = shownTotal;
    var start = performance.now();
    var duration = 320;
    var step = function (now) {
      var p = Math.min(1, (now - start) / duration);
      var eased = 1 - Math.pow(1 - p, 3);
      shownTotal = Math.round(from + (to - from) * eased);
      totalEl.textContent = Calc.formatMoney(p < 1 ? Calc.roundTo(shownTotal, 1000) : to, cfg.currency);
      if (p < 1) rafId = requestAnimationFrame(step);
    };
    rafId = requestAnimationFrame(step);
    // Страховка: если rAF притормозил (вкладка в фоне), итог всё равно станет точным
    finishTimer = setTimeout(function () { setTotalNow(to); }, duration + 80);
  }

  var liveTimer = 0;
  function announce(result) {
    clearTimeout(liveTimer);
    liveTimer = setTimeout(function () {
      liveEl.textContent = 'Итого примерно ' + Calc.formatShortMoney(result.total, cfg.currency) +
        ', срок около ' + Calc.formatMonths(result.months) + '.';
    }, 700);
  }

  var current = null;

  function renderResult(result) {
    renderTotal(result.total);
    perM2El.textContent = Calc.formatMoney(result.perM2, cfg.currency) + ' за м²';
    monthsEl.textContent = '≈ ' + Calc.formatMonths(result.months);

    barEl.innerHTML = result.items.map(function (item) {
      return '<span class="c-' + esc(item.id) + '" style="flex-grow:' + item.amount + '"></span>';
    }).join('');

    listEl.innerHTML = result.items.map(function (item) {
      var share = Math.round((item.amount / result.total) * 100);
      return '<li>' +
        '<span class="result__dot c-' + esc(item.id) + '" aria-hidden="true"></span>' +
        '<span class="result__item-label">' + esc(item.label) +
        (item.detail ? '<span class="result__item-detail">' + esc(item.detail) + ' · ' + share + '%</span>' : '<span class="result__item-detail">' + share + '%</span>') +
        '</span>' +
        '<span class="result__item-amount">' + esc(Calc.formatMoney(item.amount, cfg.currency)) + '</span>' +
        '</li>';
    }).join('');

    finishHint.textContent = cfg.finishes[result.input.finish].hint || '';
    announce(result);
  }

  function update() {
    current = Calc.calculate(readForm(), cfg);
    // Ползунок всегда показывает корректное (ограниченное) значение
    areaRange.value = current.input.area;
    updateRangeFill();
    renderResult(current);
    renderLeadSummary(current);
    stickyTotal.textContent = '≈ ' + Calc.formatShortMoney(current.total, cfg.currency);
  }

  // Мобильная плашка с итогом: пока пользователь крутит параметры, а карточка результата ниже экрана
  var sticky = $('#calc-sticky');
  var stickyTotal = $('#calc-sticky-total');
  if ('IntersectionObserver' in window) {
    var seen = { fields: false, result: false };
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        seen[entry.target === resultCard ? 'result' : 'fields'] = entry.isIntersecting;
      });
      sticky.classList.toggle('is-visible', seen.fields && !seen.result);
    }, { threshold: 0 });
    io.observe($('.calc__fields'));
    io.observe(resultCard);
  }

  form.addEventListener('input', function (e) {
    if (e.target === areaRange) areaNumber.value = areaRange.value;
    if (e.target === terraceToggle) {
      terraceArea.disabled = !terraceToggle.checked;
      if (terraceToggle.checked && !Number(terraceArea.value)) terraceArea.value = cfg.options.terrace.suggested;
    }
    update();
    track('calc_used', null, true);
  });

  // Когда пользователь закончил ввод — показываем в поле нормализованное значение
  form.addEventListener('change', function (e) {
    if (e.target === areaNumber) areaNumber.value = current.input.area;
    if (e.target === terraceArea && terraceToggle.checked) terraceArea.value = current.input.terrace;
    if (e.target === terraceToggle && terraceToggle.checked) terraceArea.focus();
  });

  form.addEventListener('submit', function (e) { e.preventDefault(); });

  // Пресеты: кнопки в технологиях и проектах
  function scrollToCalc() {
    var title = $('#calc-title');
    var target = $('#calc');
    target.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    title.focus({ preventScroll: true });
    resultCard.classList.remove('is-flash');
    void resultCard.offsetWidth; // перезапуск анимации
    resultCard.classList.add('is-flash');
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-preset]');
    if (!btn) return;
    var preset;
    try {
      preset = JSON.parse(btn.getAttribute('data-preset'));
    } catch (err) {
      console.error('[Полдень] Неверный data-preset', err);
      return;
    }
    applyState(Object.assign({}, current.input, preset));
    scrollToCalc();
    track('calc_preset', preset);
  });

  // Ссылка на расчёт
  var copyBtn = $('#copy-link');
  var copyStatus = $('#copy-status');
  var copyTimer = 0;
  copyBtn.addEventListener('click', function () {
    var base = location.href.split(/[?#]/)[0];
    var url = base + '?' + Calc.encodeState(current.input) + '#calc';
    var done = function (msg) {
      copyStatus.textContent = msg;
      clearTimeout(copyTimer);
      copyTimer = setTimeout(function () { copyStatus.textContent = ''; }, 4000);
    };
    try { history.replaceState(null, '', url); } catch (err) { /* file:// в некоторых браузерах */ }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(url).then(
        function () { done('Ссылка скопирована'); },
        function () { done('Ссылка — в адресной строке'); }
      );
    } else {
      done('Ссылка — в адресной строке');
    }
    track('calc_share');
  });

  /* =========================================================
     Проекты: цены из калькулятора и фильтр
     ========================================================= */
  var projects = $$('.project');
  projects.forEach(function (card) {
    var btn = $('[data-preset]', card);
    var priceEl = $('[data-project-price]', card);
    if (!btn || !priceEl) return;
    try {
      var r = Calc.calculate(JSON.parse(btn.getAttribute('data-preset')), cfg);
      priceEl.textContent = '≈ ' + Calc.formatShortMoney(r.total, cfg.currency);
    } catch (err) {
      console.error('[Полдень] Не удалось посчитать проект', err);
    }
  });

  var chips = $$('[data-filter]');
  var projectsCount = $('#projects-count');
  chips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      var filter = chip.getAttribute('data-filter');
      chips.forEach(function (c) { c.setAttribute('aria-pressed', String(c === chip)); });
      var visible = 0;
      projects.forEach(function (card) {
        var show = filter === 'all' || card.getAttribute('data-tech') === filter;
        card.hidden = !show;
        if (show) visible++;
      });
      projectsCount.textContent = 'Показано проектов: ' + visible;
    });
  });

  /* =========================================================
     Форма заявки
     ========================================================= */
  var leadForm = $('#lead-form');
  var nameInput = $('#lead-name');
  var phoneInput = $('#lead-phone');
  var commentInput = $('#lead-comment');
  var consentInput = $('#lead-consent');
  var attachInput = $('#lead-attach');
  var honeypot = $('#lead-website');
  var submitBtn = $('#lead-submit');
  var statusEl = $('#lead-status');
  var successEl = $('#lead-success');
  var summaryEl = $('#lead-summary');
  var attachTotalEl = $('#lead-attach-total');

  // UTM-метки запоминаем при загрузке: кнопка «Скопировать ссылку» переписывает адрес страницы,
  // и без этого метки рекламной кампании потерялись бы до отправки заявки
  var landingUtm = Form.parseUtm(location.search);
  var landingPage = location.href;

  // Пояснение «это демо, данные никуда не ушли» нужно только без подключённого бэкенда
  $('.lead-success__demo').hidden = Boolean(cfg.leadEndpoint);

  var fieldsMap = {
    name: nameInput,
    phone: phoneInput,
    comment: commentInput,
    consent: consentInput
  };

  function renderLeadSummary(result) {
    var i = result.input;
    var extras = [];
    if (i.slab) extras.push(cfg.options.slab.shortLabel);
    if (i.terrace > 0) extras.push('терраса ' + i.terrace + '\u00A0м²');
    if (i.garage) extras.push(cfg.options.garage.shortLabel);
    var rows = [
      ['Стены', cfg.technologies[i.tech].label],
      ['Площадь', i.area + '\u00A0м², ' + cfg.floors[i.floors].label],
      ['Отделка', cfg.finishes[i.finish].label],
      ['Опции', extras.length ? extras.join(', ') : 'нет'],
      ['Срок', '≈ ' + Calc.formatMonths(result.months)]
    ];
    summaryEl.innerHTML = rows.map(function (row) {
      return '<dt>' + esc(row[0]) + '</dt><dd>' + esc(row[1]) + '</dd>';
    }).join('') +
      '<dt class="is-total">Итого</dt><dd class="is-total">≈ ' + esc(Calc.formatMoney(result.total, cfg.currency)) + '</dd>';
    attachTotalEl.textContent = '≈ ' + Calc.formatShortMoney(result.total, cfg.currency) + ', ' +
      cfg.technologies[i.tech].label.toLowerCase() + ', ' + i.area + '\u00A0м²';
  }

  // Маска телефона
  phoneInput.addEventListener('input', function () {
    var caret = phoneInput.selectionStart == null ? phoneInput.value.length : phoneInput.selectionStart;
    var r = Form.reformatPhone(phoneInput.value, caret);
    phoneInput.value = r.value;
    if (document.activeElement === phoneInput) phoneInput.setSelectionRange(r.caret, r.caret);
  });
  phoneInput.addEventListener('keydown', function (e) {
    if (e.key !== 'Backspace' || phoneInput.selectionStart !== phoneInput.selectionEnd) return;
    var r = Form.phoneBackspace(phoneInput.value, phoneInput.selectionStart);
    if (!r) return;
    e.preventDefault();
    phoneInput.value = r.value;
    phoneInput.setSelectionRange(r.caret, r.caret);
  });

  function setError(key, message) {
    var input = fieldsMap[key];
    var errEl = document.getElementById(input.id + '-error');
    if (message) {
      input.setAttribute('aria-invalid', 'true');
      errEl.textContent = message;
      errEl.hidden = false;
    } else {
      input.removeAttribute('aria-invalid');
      errEl.textContent = '';
      errEl.hidden = true;
    }
  }

  Object.keys(fieldsMap).forEach(function (key) {
    var input = fieldsMap[key];
    input.addEventListener(input.type === 'checkbox' ? 'change' : 'input', function () {
      if (input.getAttribute('aria-invalid') === 'true') setError(key, '');
    });
  });

  function readLead() {
    return {
      name: nameInput.value,
      phone: phoneInput.value,
      comment: commentInput.value,
      consent: consentInput.checked,
      attach: attachInput.checked,
      website: honeypot.value
    };
  }

  function sendLead(payload) {
    if (!cfg.leadEndpoint) {
      // Демо-режим: бэкенда нет — показываем, что именно ушло бы на сервер
      console.info('%c[Демо] Заявка не отправлена — бэкенд не подключён. Payload:', 'color:#b8471f;font-weight:bold', payload);
      console.info(JSON.stringify(payload, null, 2));
      return new Promise(function (resolve) { setTimeout(function () { resolve({ ok: true, demo: true }); }, 700); });
    }
    return fetch(cfg.leadEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json().catch(function () { return { ok: true }; });
    });
  }

  function setBusy(busy) {
    submitBtn.classList.toggle('is-busy', busy);
    submitBtn.setAttribute('aria-disabled', String(busy));
    $('.btn__label', submitBtn).textContent = busy ? 'Отправляем…' : 'Отправить заявку';
  }

  var sending = false;
  leadForm.addEventListener('submit', function (e) {
    e.preventDefault();
    if (sending) return;
    statusEl.textContent = '';

    var fields = readLead();
    var check = Form.validateLead(fields);
    Object.keys(fieldsMap).forEach(function (key) { setError(key, check.errors[key]); });
    if (!check.valid) {
      var firstKey = Object.keys(fieldsMap).filter(function (k) { return check.errors[k]; })[0];
      fieldsMap[firstKey].focus();
      track('lead_error', { fields: Object.keys(check.errors) });
      return;
    }

    var calc = fields.attach ? { result: current, summary: Calc.formatCalcSummary(current, cfg) } : null;
    var payload = Form.buildLeadPayload(fields, calc, {
      page: landingPage,
      submittedAt: new Date().toISOString(),
      utm: landingUtm
    });

    // Бот заполнил скрытое поле — делаем вид, что всё хорошо, но ничего не отправляем
    if (fields.website) {
      showSuccess(fields.name);
      return;
    }

    sending = true;
    setBusy(true);
    sendLead(payload).then(function () {
      track('lead_submit', { total: calc ? current.total : null });
      showSuccess(fields.name);
    }).catch(function (err) {
      console.error('[Полдень] Ошибка отправки заявки', err);
      statusEl.textContent = 'Не удалось отправить заявку. Попробуйте ещё раз или позвоните: +7 (000) 000-00-00.';
    }).then(function () {
      sending = false;
      setBusy(false);
    });
  });

  function showSuccess(name) {
    var clean = String(name || '').trim();
    $('#lead-success-text').textContent = (clean ? 'Спасибо, ' + clean + '! ' : 'Спасибо! ') +
      'Инженер перезвонит в течение 15 минут в рабочее время.';
    leadForm.hidden = true;
    successEl.hidden = false;
    $('#lead-success-title').focus();
  }

  $('#lead-again').addEventListener('click', function () {
    leadForm.reset();
    Object.keys(fieldsMap).forEach(function (key) { setError(key, ''); });
    successEl.hidden = true;
    leadForm.hidden = false;
    nameInput.focus();
  });

  /* =========================================================
     FAQ: одновременно открыт один ответ
     (атрибут name у <details> делает это сам в новых браузерах)
     ========================================================= */
  var faqItems = $$('.faq__item');
  var nativeExclusive = 'name' in HTMLDetailsElement.prototype;
  faqItems.forEach(function (item) {
    var summary = $('summary', item);
    summary.addEventListener('click', function () {
      // click срабатывает до переключения: закрытый сейчас — значит, открывается
      if (!item.open) track('faq_open', { question: summary.textContent.trim() });
    });
    item.addEventListener('toggle', function () {
      if (item.open && !nativeExclusive) {
        faqItems.forEach(function (other) { if (other !== item) other.open = false; });
      }
    });
  });

  /* =========================================================
     Политика конфиденциальности (диалог)
     ========================================================= */
  var dialog = $('#privacy-dialog');
  $$('[data-open-privacy]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (typeof dialog.showModal === 'function') dialog.showModal();
      else dialog.setAttribute('open', '');
    });
  });
  dialog.addEventListener('click', function (e) {
    if (e.target === dialog) dialog.close(); // клик по подложке
  });

  $('#year').textContent = new Date().getFullYear();

  /* =========================================================
     Старт: состояние из ссылки (?area=…&tech=…) или значения по умолчанию
     ========================================================= */
  var shared = Calc.decodeState(location.search, cfg);
  applyState(shared || cfg.defaults);

  // Ссылка «поделиться расчётом» открывает страницу сразу на калькуляторе.
  // Докручиваем после загрузки шрифтов: они меняют высоту блоков выше.
  if (shared || location.hash) {
    window.addEventListener('load', function () {
      var target = document.getElementById(location.hash.slice(1)) || (shared && $('#calc'));
      if (target && window.scrollY < 10) target.scrollIntoView({ block: 'start', behavior: 'instant' });
    });
  }
})();
