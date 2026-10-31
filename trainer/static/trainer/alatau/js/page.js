'use strict';
/* =========================================================
   Алатау — виртуальные заезды. Весь код написан с нуля.
   ========================================================= */
const $ = s => document.querySelector(s);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const lerp = (a, b, t) => a + (b - a) * t;
/* ---------------- Language of the page: ru, kk, en ---------------- */
// The site's page passes its language in the address (?lang=); without it the page speaks Russian,
// the site's default. The words of each language are in alatau/text/<lang>.js, one file each.
const LANG = (q => ['ru', 'kk', 'en'].includes(q) ? q : 'ru')(new URLSearchParams(location.search).get('lang'));
const LOCALE = { ru: 'ru-RU', kk: 'kk-KZ', en: 'en-GB' }[LANG];
const TEXT = { ru: TEXT_RU, kk: TEXT_KK, en: TEXT_EN };
