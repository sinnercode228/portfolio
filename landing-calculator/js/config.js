/*!
 * Конфигурация калькулятора «Полдень» (демо-проект).
 * Все цены вымышленные. Меняйте значения здесь — страница и расчёт подхватят их сами.
 * Файл работает и в браузере (window.HOUSE_CONFIG), и в Node (require).
 */
(function (root, factory) {
  'use strict';
  var config = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = config;
  } else {
    root.HOUSE_CONFIG = config;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  return {
    currency: '₽',
    /** Шаг округления сумм в разбивке, ₽ */
    rounding: 1000,

    /** Площадь дома, м² */
    area: { min: 40, max: 400, step: 1 },

    /** Этажность: коэффициент к цене коробки за м² (у двухэтажного дома меньше фундамента и кровли на 1 м²) */
    floors: {
      1: { label: '1 этаж', coef: 1 },
      2: { label: '2 этажа', coef: 0.94 }
    },

    /** Технология стен: цена коробки за м² и базовый срок, мес. */
    technologies: {
      aerated: { label: 'Газобетон', price: 31000, months: 5 },
      frame: { label: 'Каркас', price: 24000, months: 3 },
      brick: { label: 'Кирпич', price: 43000, months: 7 },
      timber: { label: 'Брус', price: 28000, months: 4 }
    },

    /** Уровень отделки: множитель к стоимости коробки и дополнительный срок, мес. */
    finishes: {
      shell: {
        label: 'Коробка',
        multiplier: 1,
        months: 0,
        hint: 'Стены, перекрытия, кровля, окна и входная дверь.'
      },
      whitebox: {
        label: 'White box',
        multiplier: 1.3,
        months: 1.5,
        hint: 'Коробка + инженерные сети, стяжка, штукатурка, фасад.'
      },
      turnkey: {
        label: 'Под ключ',
        multiplier: 1.65,
        months: 3,
        hint: 'White box + чистовая отделка, сантехника, свет — можно заезжать.'
      }
    },

    /** Дополнительные опции */
    options: {
      slab: {
        label: 'Фундамент — монолитная плита',
        shortLabel: 'фундамент-плита',
        pricePerM2: 7500,
        /** плита больше пятна дома на 10 % (свесы, отмостка) */
        overhang: 0.1
      },
      terrace: {
        label: 'Терраса',
        pricePerM2: 12000,
        min: 6,
        max: 80,
        suggested: 20
      },
      garage: {
        label: 'Гараж на 1 автомобиль',
        shortLabel: 'гараж',
        price: 950000
      }
    },

    /** Значения калькулятора по умолчанию */
    defaults: {
      area: 120,
      floors: 1,
      tech: 'aerated',
      finish: 'whitebox',
      slab: true,
      terrace: 0,
      garage: false
    },

    /**
     * Куда отправлять заявки (POST, JSON). Пусто — демо-режим: payload пишется в консоль.
     * Пример: 'https://lead.example.workers.dev' — см. serverless/telegram-lead.mjs и README.
     */
    leadEndpoint: ''
  };
});
