'use strict';
/* ---------------- Слова страницы: t(), формы числа, единицы и перевод разметки ---------------- */
// t(key, { name }) fills {name}; a key missing in a language falls back to Russian, then to the key
function t(key, vars) {
  const s = (TEXT[LANG][key] != null ? TEXT[LANG] : TEXT.ru)[key] ?? key;
  return vars ? s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m)) : s;
}
const tr = t; // the same, for the functions that keep the ride time in a local `t`
const langPath = p => p.replace(/^\/(ru|kk|en)\//, '/' + LANG + '/'); // a site address in the language of the page
const PLURAL = new Intl.PluralRules(LOCALE);
function tn(key, n) { const f = t(key); return typeof f === 'string' ? f : (f[PLURAL.select(n)] || f.other); }
const L = o => o[LANG] || o.ru; // a name in the route catalogue: { ru, kk, en }
const lc = s => LANG === 'en' ? s : s.toLowerCase(); // a type name inside a sentence
const numF = (v, d) => v.toFixed(d).replace('.', LANG === 'en' ? '.' : ',');
const durLabel = sec => sec < 60 ? sec + ' ' + t('u.s') : sec < 3600 ? sec / 60 + ' ' + t('u.min') : sec / 3600 + ' ' + t('u.h');
document.documentElement.lang = LANG; document.title = t('title');
document.querySelectorAll('[data-t]').forEach(el => { el.textContent = t(el.dataset.t); });
document.querySelectorAll('[data-t-label]').forEach(el => el.setAttribute('aria-label', t(el.dataset.tLabel)));
document.querySelectorAll('[data-t-alt]').forEach(el => el.setAttribute('alt', t(el.dataset.tAlt)));
document.querySelectorAll('[data-tyre]').forEach(o => { o.textContent = o.dataset.tyre + ' — ' + o.value + ' ' + t('u.mm'); });
document.querySelectorAll('#mpDelay option').forEach(o => { o.textContent = t('mp.startIn', { t: durLabel(+o.value) }); });
const fmt1 = v => numF(v, 1);
