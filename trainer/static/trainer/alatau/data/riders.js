'use strict';
/* ---------------- Гонщики: стили, персонажи, форма и типы велосипедов ---------------- */
const STYLES = {
  climber: { name: 'Горняк', hint: 'сильнее на подъёмах' },
  sprinter: { name: 'Спринтер', hint: 'взрывной финиш' },
  rouleur: { name: 'Раздельщик', hint: 'ровный темп на равнине' },
  attacker: { name: 'Атакующий', hint: 'рваные ускорения' },
  allround: { name: 'Универсал', hint: 'без слабых мест' }
};
// a — основной цвет формы, b — узор, pat — тип узора. Никаких надписей и логотипов.
const CHARS = [
  { id: 'aybar', name: L({ ru: "Айбар", kk: "Айбар", en: "Aibar" }), style: 'climber', a: 0x1f4e8c, b: 0xeef2f6, pat: 'peaks', helmet: 0xeef2f6, bike: 0x1f4e8c, skin: 0xc68e62, shoe: 0xeef2f6, hair: 'none', mass: 64, size: .97 },
  { id: 'dana', name: L({ ru: "Дана", kk: "Дана", en: "Dana" }), style: 'sprinter', a: 0xc3323b, b: 0xe8a33a, pat: 'split', helmet: 0x1d2024, bike: 0x26292e, skin: 0xd9a77f, shoe: 0x1d2024, hair: 'pony', hairC: 0x2a1b12, mass: 62, size: .95 },
  { id: 'erlan', name: L({ ru: "Ерлан", kk: "Ерлан", en: "Erlan" }), style: 'rouleur', a: 0x33383f, b: 0xa8d03c, pat: 'sash', helmet: 0xa8d03c, bike: 0x33383f, skin: 0xb98159, shoe: 0x1d2024, hair: 'beard', hairC: 0x1f1610, mass: 80, size: 1.04, deep: true },
  { id: 'madina', name: L({ ru: "Мадина", kk: "Мадина", en: "Madina" }), style: 'attacker', a: 0x1f9aa3, b: 0xf07b5a, pat: 'hoops', helmet: 0xf07b5a, bike: 0xf4f6f8, skin: 0xe2b48c, shoe: 0xf4f6f8, hair: 'pony', hairC: 0x120c08, mass: 58, size: .94 },
  { id: 'timur', name: L({ ru: "Тимур", kk: "Тимур", en: "Timur" }), style: 'allround', a: 0xc28a2e, b: 0x2f4a33, pat: 'stripes', helmet: 0x2f4a33, bike: 0x2f4a33, skin: 0xa8734c, shoe: 0x1d2024, hair: 'none', mass: 72, size: 1 },
  { id: 'aliya', name: L({ ru: "Алия", kk: "Әлия", en: "Aliya" }), style: 'climber', a: 0x6d4fb0, b: 0xf4f6f8, pat: 'chevron', helmet: 0xf4f6f8, bike: 0x6d4fb0, skin: 0xd9a77f, shoe: 0x6d4fb0, hair: 'pony', hairC: 0x5a3a22, mass: 54, size: .93 },
  { id: 'nurzhan', name: L({ ru: "Нуржан", kk: "Нұржан", en: "Nurzhan" }), style: 'sprinter', a: 0xe0702c, b: 0x1c2f5a, pat: 'bands', helmet: 0x1c2f5a, bike: 0xe0702c, skin: 0xc0875a, shoe: 0xf4f6f8, hair: 'none', mass: 78, size: 1.03, deep: true },
  { id: 'saule', name: L({ ru: "Сауле", kk: "Сәуле", en: "Saule" }), style: 'allround', a: 0xf0c430, b: 0x2b2e33, pat: 'sun', helmet: 0x2b2e33, bike: 0x2b2e33, skin: 0xe8c09a, shoe: 0x2b2e33, hair: 'pony', hairC: 0x8a5a2b, mass: 60, size: .96 },
  { id: 'arman', name: L({ ru: "Арман", kk: "Арман", en: "Arman" }), style: 'rouleur', a: 0x17191c, b: 0xaab2bb, pat: 'pin', helmet: 0xaab2bb, bike: 0x17191c, skin: 0xb07a50, shoe: 0x17191c, hair: 'beard', hairC: 0x15100c, mass: 77, size: 1.02, deep: true },
  { id: 'zhanna', name: L({ ru: "Жанна", kk: "Жанна", en: "Zhanna" }), style: 'attacker', a: 0xb53f7a, b: 0x2aa39a, pat: 'diag', helmet: 0x2aa39a, bike: 0xb53f7a, skin: 0xd6a27a, shoe: 0xf4f6f8, hair: 'pony', hairC: 0x2a1b12, mass: 59, size: .95 },
  { id: 'ilyas', name: L({ ru: "Ильяс", kk: "Ілияс", en: "Ilyas" }), style: 'climber', a: 0x2c7a4b, b: 0x101214, pat: 'dots', helmet: 0x101214, bike: 0x2c7a4b, skin: 0xc68e62, shoe: 0x101214, hair: 'none', mass: 63, size: .97 },
  { id: 'kamila', name: L({ ru: "Камила", kk: "Камила", en: "Kamila" }), style: 'allround', a: 0x3d7bb6, b: 0xe9f1f8, pat: 'wave', helmet: 0xe9f1f8, bike: 0xe9f1f8, skin: 0xe2b48c, shoe: 0x3d7bb6, hair: 'pony', hairC: 0x1a120c, mass: 57, size: .94 }
];
// гонщик игрока: одна модель в форме UBT
const PLAYER_CH = { id: 'me', name: t('you'), style: 'allround', a: 0xEE6A1F, b: 0x17181a, pat: 'ornament', helmet: 0x17181a, stripe: 0xEE6A1F, glass: 0x101216, bike: 0x17181a, rim: 0xEE6A1F, deep: true, skin: 0xeec3a0, shoe: 0xf4f6f8, hair: 'none', mass: 75, size: 1, build: 1 };
const charById = id => CHARS.find(c => c.id === id) || PLAYER_CH;
// Формы, которые можно надеть на любого героя (без логотипов и надписей)
const KITS = {
  ubt: { name: 'UBT', over: { a: 0xEE6A1F, b: 0x17181a, trim: 0x17181a, pat: 'ornament', sleeve: 0xEE6A1F, sleeveTex: true, cuff: 0xFFD21F, orn: 0xFFD21F, bib: 0x17181a, backText: 'UBT' } }
};
// Популярные типы велосипедов: типичный вес, сопротивление качению (шины), посадка (аэродинамика), типичное колесо
const BIKE_TYPES = {
  road: { name: L({ ru: "Шоссейный", kk: "Шоссейлік", en: "Road" }), kg: 8.5, crr: .0045, aero: 1.0, circ: 2105, tire: .021 },
  aero: { name: L({ ru: "Аэро-шоссейный", kk: "Аэро шоссейлік", en: "Aero road" }), kg: 8.0, crr: .0042, aero: .94, circ: 2105, tire: .021 },
  tt: { name: L({ ru: "Разделочный (ТТ)", kk: "TT (жеке старт)", en: "Time trial (TT)" }), kg: 9.0, crr: .0042, aero: .8, circ: 2105, tire: .02 },
  gravel: { name: L({ ru: "Гравийный", kk: "Гравел", en: "Gravel" }), kg: 9.8, crr: .0058, aero: 1.06, circ: 2200, tire: .03 },
  hybrid: { name: L({ ru: "Гибрид / городской", kk: "Гибрид / қалалық", en: "Hybrid / city" }), kg: 13, crr: .0065, aero: 1.22, circ: 2136, tire: .028 },
  mtb: { name: L({ ru: "Горный хардтейл", kk: "Тау хардтейлі", en: "Mountain hardtail" }), kg: 12.5, crr: .0085, aero: 1.18, circ: 2288, tire: .042 },
  fs: { name: L({ ru: "Горный двухподвес", kk: "Екі амортизаторлы тау велосипеді", en: "Full-suspension mountain" }), kg: 14.5, crr: .009, aero: 1.2, circ: 2288, tire: .045 }
};
