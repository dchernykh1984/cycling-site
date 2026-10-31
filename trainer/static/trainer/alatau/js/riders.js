'use strict';
/* ---------------- Персонажи: оригинальные гонщики, без логотипов, надписей и узнаваемых образов ---------------- */
const hexs = c => '#' + c.toString(16).padStart(6, '0');
function jerseyTex(ch) {
  const t = canvasTex(512, 256, (g, w, h) => {
    const cx = w / 2; // центр холста = грудь (смещение текстуры ниже)
    g.fillStyle = hexs(ch.a); g.fillRect(0, 0, w, h); g.fillStyle = hexs(ch.b);
    switch (ch.pat) {
      case 'wing': { // золотой шеврон из крыльев беркута
        const y0 = h * .34;
        for (const s of [-1, 1]) {
          for (let k = 0; k < 5; k++) {
            g.beginPath(); const x = cx + s * (14 + k * 30), yy = y0 + k * 9;
            g.moveTo(cx, y0 + 46); g.lineTo(x, yy); g.lineTo(x + s * 30, yy + 4); g.lineTo(x + s * 22, yy + 26); g.lineTo(cx, y0 + 80); g.closePath(); g.fill();
          }
        }
        g.fillStyle = hexs(ch.a); g.beginPath(); g.moveTo(cx, y0 + 58); g.lineTo(cx - 12, y0 + 82); g.lineTo(cx + 12, y0 + 82); g.closePath(); g.fill();
        g.fillStyle = hexs(ch.b); g.fillRect(0, h - 14, w, 6); break;
      }
      case 'leopard': { // мягкие пятна ирбиса
        const r = rng(42);
        for (let i = 0; i < 70; i++) {
          const x = r() * w, y = r() * h, s = 7 + r() * 9;
          for (let k = 0; k < 5; k++) { const a = k / 5 * 6.283 + r() * .5; g.fillStyle = 'rgba(70,74,80,.55)'; g.beginPath(); g.ellipse(x + Math.cos(a) * s, y + Math.sin(a) * s * .8, 3.6, 2.6, a, 0, 7); g.fill(); }
          g.fillStyle = 'rgba(150,156,162,.35)'; g.beginPath(); g.arc(x, y, s * .55, 0, 7); g.fill();
        }
        break;
      }
      case 'apple': { // круглая эмблема с яблоком
        const ey = h * .46, R = 46;
        g.fillStyle = hexs(ch.b); g.beginPath(); g.arc(cx, ey, R, 0, 7); g.fill();
        g.fillStyle = hexs(ch.a); g.beginPath(); g.arc(cx - 12, ey + 4, 21, 0, 7); g.arc(cx + 12, ey + 4, 21, 0, 7); g.fill();
        g.beginPath(); g.moveTo(cx - 28, ey + 10); g.quadraticCurveTo(cx, ey + 44, cx + 28, ey + 10); g.fill();
        g.strokeStyle = '#6b4a2b'; g.lineWidth = 4; g.beginPath(); g.moveTo(cx, ey - 12); g.quadraticCurveTo(cx + 2, ey - 24, cx + 6, ey - 30); g.stroke();
        g.fillStyle = hexs(ch.leaf || 0x3f9a46); g.beginPath(); g.ellipse(cx + 18, ey - 26, 13, 6, -.5, 0, 7); g.fill();
        g.fillStyle = hexs(ch.b); g.fillRect(0, h - 14, w, 6); break;
      }
      case 'ornament': { // оранжевая форма: полосы на груди, молния, флаг и горы на спине
        g.fillStyle = '#3a3a3a'; g.fillRect(cx - 2, 0, 4, h);
        g.fillStyle = hexs(ch.b);
        for (let k = 0; k < 3; k++) { const y = h * .4 + k * 17;
          g.beginPath(); g.moveTo(cx - 150, y + 4); g.lineTo(cx - 40, y); g.lineTo(cx - 40, y + 9); g.lineTo(cx - 150, y + 13); g.closePath(); g.fill();
          g.beginPath(); g.moveTo(cx + 150, y + 4); g.lineTo(cx + 40, y); g.lineTo(cx + 40, y + 9); g.lineTo(cx + 150, y + 13); g.closePath(); g.fill(); }
        for (const x0 of [0, w]) { // спина — края холста
          g.fillStyle = '#00AFCA'; g.fillRect(x0 - 26, 34, 52, 32); g.fillStyle = '#FFD21F'; g.beginPath(); g.arc(x0, 50, 8, 0, 7); g.fill();
          g.fillStyle = hexs(ch.b); g.beginPath(); g.moveTo(x0 - 90, h - 26); g.lineTo(x0 - 50, h - 70); g.lineTo(x0 - 30, h - 50); g.lineTo(x0, h - 92); g.lineTo(x0 + 34, h - 48); g.lineTo(x0 + 52, h - 64); g.lineTo(x0 + 90, h - 26); g.closePath(); g.fill();
          g.fillStyle = hexs(ch.a); g.beginPath(); g.moveTo(x0 - 8, h - 80); g.lineTo(x0, h - 92); g.lineTo(x0 + 9, h - 79); g.lineTo(x0 + 2, h - 84); g.closePath(); g.fill();
          if (ch.backText) { // надпись на спине (шов холста проходит по центру спины)
            g.save(); g.translate(x0, h * .5); g.fillStyle = hexs(ch.b); g.font = '700 54px Unbounded, "Arial Black", sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(ch.backText, 0, 0); g.restore();
          }
        }
        break;
      }
      case 'stripes': for (let i = 0; i < 4; i++) g.fillRect(0, 32 + i * 56, w, 18); break;
      case 'hoops': g.fillRect(0, h * .4, w, h * .22); break;
      case 'split': g.fillRect(0, 0, w / 2, h); break;
      case 'chevron': for (let x = 0; x < w; x += 64) { g.beginPath(); g.moveTo(x, h * .3); g.lineTo(x + 32, h * .52); g.lineTo(x + 64, h * .3); g.lineTo(x + 64, h * .46); g.lineTo(x + 32, h * .68); g.lineTo(x, h * .46); g.closePath(); g.fill(); } break;
      case 'sash': g.save(); g.translate(w / 2, h / 2); g.rotate(-.55); g.fillRect(-w, -26, w * 2, 52); g.restore(); break;
      case 'peaks': g.beginPath(); g.moveTo(0, h); for (let x = 0; x <= w; x += 64) { g.lineTo(x + 32, h * .38); g.lineTo(x + 64, h * .72); } g.lineTo(w, h); g.closePath(); g.fill(); break;
      case 'bands': g.fillRect(0, 0, w, h * .24); g.fillRect(0, h * .76, w, h * .24); break;
      case 'sun': for (let k = 0; k < 16; k++) { g.save(); g.translate(w * .5, h * 1.1); g.rotate(-Math.PI / 2 + (k - 7.5) * .19); g.fillRect(-6, 0, 12, -h * 1.2); g.restore(); } break;
      case 'pin': for (let x = 8; x < w; x += 28) g.fillRect(x, 0, 6, h); break;
      case 'diag': for (let x = -h; x < w + h; x += 80) { g.beginPath(); g.moveTo(x, h); g.lineTo(x + h, 0); g.lineTo(x + h + 30, 0); g.lineTo(x + 30, h); g.closePath(); g.fill(); } break;
      case 'dots': for (let y = 20; y < h; y += 44) for (let x = (y / 44 % 2) * 22 + 12; x < w; x += 44) { g.beginPath(); g.arc(x, y, 10, 0, 7); g.fill(); } break;
      case 'wave': g.beginPath(); g.moveTo(0, h); for (let x = 0; x <= w; x += 4) g.lineTo(x, h * .55 + Math.sin(x / 40) * 20); g.lineTo(w, h); g.closePath(); g.fill(); break;
    }
    g.fillStyle = hexs(ch.trim || ch.b); g.fillRect(0, 0, w, 10);
  });
  t.wrapS = THREE.RepeatWrapping; t.offset.x = .5;
  return t;
}
// казахский орнамент «қошқар мүйіз» (бараньи рога) — традиционный мотив
function ramHorn(g, x, y, s, col) {
  g.save(); g.translate(x, y); g.scale(s, s); g.strokeStyle = col; g.fillStyle = col; g.lineWidth = 7; g.lineCap = 'round';
  for (const k of [-1, 1]) {
    g.beginPath(); g.moveTo(0, 14); g.bezierCurveTo(k * 6, -4, k * 30, -6, k * 32, -24); g.bezierCurveTo(k * 34, -42, k * 15, -46, k * 12, -33); g.bezierCurveTo(k * 10, -25, k * 18, -21, k * 22, -28); g.stroke();
    g.beginPath(); g.moveTo(0, 14); g.bezierCurveTo(k * 8, 26, k * 28, 28, k * 30, 44); g.bezierCurveTo(k * 31, 58, k * 17, 60, k * 15, 51); g.stroke();
  }
  g.beginPath(); g.moveTo(0, -46); g.lineTo(-8, -30); g.lineTo(0, -18); g.lineTo(8, -30); g.closePath(); g.fill();
  g.beginPath(); g.moveTo(0, -18); g.lineTo(0, 58); g.stroke();
  g.restore();
}
function sleeveTex(ch) {
  return canvasTex(128, 128, (g, w, h) => {
    g.fillStyle = hexs(ch.a); g.fillRect(0, 0, w, h);
    g.fillStyle = hexs(ch.cuff); g.fillRect(0, 0, w, h * .26);
    ramHorn(g, w * .25, h * .62, .55, hexs(ch.orn)); ramHorn(g, w * .75, h * .62, .55, hexs(ch.orn));
  });
}
const UPV = new THREE.Vector3(0, 1, 0), _sv = new THREE.Vector3();
function placeSeg(m, a, b) { _sv.subVectors(b, a); const L = _sv.length() || 1e-4; m.position.copy(a).addScaledVector(_sv, .5); m.quaternion.setFromUnitVectors(UPV, _sv.multiplyScalar(1 / L)); m.scale.y = L; }
function makeRider(ch) {
  const g = new THREE.Group(); g.rotation.order = 'YXZ';
  const L = c => new THREE.MeshLambertMaterial({ color: c });
  const mFrame = L(ch.bike), mDark = L(0x1c1f23), mTire = L(0x151618), mRim = L(ch.rim || 0xb9bec4), mSkin = L(ch.skin), mBib = L(ch.bib || 0x16191d), mHelm = L(ch.helmet), mShoe = L(ch.shoe), mSleeve = ch.sleeveTex ? new THREE.MeshLambertMaterial({ map: sleeveTex(ch) }) : L(ch.sleeve || ch.a), mSleeveBall = L(ch.sleeve || ch.a);
  const mGlass = new THREE.MeshStandardMaterial({ color: ch.glass || 0x0d0f12, metalness: ch.mirror ? .9 : .2, roughness: ch.mirror ? .15 : .4, emissive: ch.mirror ? ch.glass : 0, emissiveIntensity: ch.mirror ? .25 : 0 });
  const mJersey = new THREE.MeshLambertMaterial({ map: jerseyTex(ch) });
  const V = (x, y, z) => new THREE.Vector3(x, y, z);
  const tube = (a, b, r, m, r2) => { const t = new THREE.Mesh(new THREE.CylinderGeometry(r, r2 == null ? r : r2, 1, 12), m); placeSeg(t, a, b); g.add(t); return t; };
  const ball = (p, r, m) => { const s = new THREE.Mesh(new THREE.SphereGeometry(r, 16, 12), m); s.position.copy(p); g.add(s); return s; };
  // велосипед
  [.52, -.48].forEach(z => {
    const tire = new THREE.Mesh(new THREE.TorusGeometry(.335, ch.tire || .021, 8, 30), mTire); tire.rotation.y = Math.PI / 2; tire.position.set(0, .34, z); g.add(tire);
    const rim = new THREE.Mesh(new THREE.TorusGeometry(.305, ch.deep ? .03 : .014, 6, 30), mRim); rim.rotation.y = Math.PI / 2; rim.position.set(0, .34, z); g.add(rim);
    const hub = new THREE.Mesh(new THREE.CylinderGeometry(.025, .025, .11, 8), mDark); hub.rotation.z = Math.PI / 2; hub.position.set(0, .34, z); g.add(hub);
    for (let k = 0; k < 6; k++) { const a = k / 6 * Math.PI * 2; tube(V(0, .34, z), V(0, .34 + Math.sin(a) * .3, z + Math.cos(a) * .3), .004, mRim); }
  });
  const BB = V(0, .3, .03), S = V(0, .82, -.16), H = V(0, .86, .41), Hb = V(0, .74, .45), R = V(0, .34, -.48), F = V(0, .34, .52);
  tube(BB, S, .022, mFrame); tube(S, H, .02, mFrame); tube(BB, Hb, .026, mFrame); tube(BB, R, .015, mFrame); tube(S, R, .013, mFrame); tube(Hb, F, .017, mFrame); tube(Hb, H, .028, mFrame);
  tube(S, V(0, .95, -.2), .013, mDark);
  const saddle = new THREE.Mesh(new THREE.BoxGeometry(.11, .035, .26), mDark); saddle.position.set(0, .965, -.19); g.add(saddle);
  tube(H, V(0, .93, .49), .016, mDark); tube(V(-.21, .94, .5), V(.21, .94, .5), .013, mDark);
  [-1, 1].forEach(s => { tube(V(s * .21, .94, .5), V(s * .21, .86, .56), .012, mDark); tube(V(s * .21, .86, .56), V(s * .21, .82, .48), .012, mDark); });
  const ring = new THREE.Mesh(new THREE.TorusGeometry(.1, .008, 6, 24), mRim); ring.rotation.y = Math.PI / 2; ring.position.set(.07, .3, .03); g.add(ring);
  // гонщик: мультяшные пропорции, голова чуть крупнее
  const bw = ch.build || 1, hip = V(0, 1.0, -.17), sh = V(0, 1.36, .23);
  ball(hip, .14, mBib).scale.set(1.15 * bw, .9, 1.1);
  const torso = tube(hip, sh, .155, mJersey, .135); torso.scale.x = 1.25 * bw; torso.scale.z = .85 * bw;
  ball(sh, .135, mSleeveBall).scale.set(1.45 * bw, .8, .9);
  tube(sh, V(0, 1.47, .34), .05, mSkin);
  const hc = V(0, 1.53, .39), hr = .128; ball(hc, hr, mSkin).scale.set(1, 1.04, 1);
  const helm = new THREE.Mesh(new THREE.SphereGeometry(hr * 1.2, 20, 12, 0, Math.PI * 2, 0, Math.PI * .56), mHelm); helm.position.set(0, 1.585, .37); helm.scale.set(1, .85, 1.2); helm.rotation.x = .12; g.add(helm);
  if (ch.helmetType === 'aero') { // каплевидный хвост и полоса
    const tail = new THREE.Mesh(new THREE.SphereGeometry(.1, 14, 10), mHelm); tail.position.set(0, 1.6, .22); tail.scale.set(1.0, .7, 2.0); tail.rotation.x = -.28; g.add(tail);
    const stripe = new THREE.Mesh(new THREE.BoxGeometry(.045, .02, .22), L(ch.stripe)); stripe.position.set(0, 1.705, .37); stripe.rotation.x = .05; g.add(stripe);
  }
  if (ch.helmetType === 'cat') { // два вентиляционных «ушка»
    [-1, 1].forEach(s => { const e = new THREE.Mesh(new THREE.ConeGeometry(.035, .07, 4), mHelm); e.position.set(s * .075, 1.73, .37); e.rotation.z = -s * .35; e.rotation.x = .2; g.add(e); const inner = new THREE.Mesh(new THREE.ConeGeometry(.018, .045, 4), mDark); inner.position.set(s * .075, 1.725, .385); inner.rotation.copy(e.rotation); g.add(inner); });
  }
  const glasses = new THREE.Mesh(new THREE.BoxGeometry(.24, .05, .035), mGlass); glasses.position.set(0, 1.525, .515); g.add(glasses);
  [-1, 1].forEach(s => { const arm = new THREE.Mesh(new THREE.BoxGeometry(.012, .012, .13), mDark); arm.position.set(s * .125, 1.53, .45); g.add(arm); });
  const mouth = new THREE.Mesh(new THREE.TorusGeometry(.032, .007, 6, 12, Math.PI), L(0x5a2a22)); mouth.rotation.z = Math.PI; mouth.position.set(0, 1.47, .508); mouth.rotation.x = -.2; g.add(mouth);
  if (ch.hair === 'pony') { const p = ball(V(0, 1.49, .22), .05, L(ch.hairC)); p.scale.set(.8, 1.6, .8); }
  if (ch.hair === 'beard') { const b = new THREE.Mesh(new THREE.SphereGeometry(.1, 12, 8, 0, Math.PI * 2, Math.PI * .5, Math.PI * .5), L(ch.hairC)); b.position.set(0, 1.49, .41); g.add(b); }
  if (ch.hair === 'braids') { // две короткие косички
    const mh = L(ch.hairC);
    [-1, 1].forEach(s => { for (let k = 0; k < 3; k++) ball(V(s * (.1 + k * .008), 1.47 - k * .045, .3 - k * .02), .033 - k * .004, mh); ball(V(s * .118, 1.345, .255), .018, L(ch.tie || 0xf3e3c3)); });
  }
  [-1, 1].forEach(s => {
    const so = V(s * .2 * bw, 1.33, .23), el = V(s * .21, 1.12, .34), ha = V(s * .21, .97, .5);
    tube(so, el, .055 * bw, mSleeve, .048 * bw); ball(el, .045, mSkin); tube(el, ha, .042 * bw, mSkin, .036); ball(ha, .045, mDark);
  });
  const legs = [-1, 1].map(s => {
    const thigh = new THREE.Mesh(new THREE.CylinderGeometry(.08 * bw, .062, 1, 10), mBib), shin = new THREE.Mesh(new THREE.CylinderGeometry(.056 * bw, .04, 1, 10), mSkin);
    const knee = new THREE.Mesh(new THREE.SphereGeometry(.058, 10, 8), mSkin), shoe = new THREE.Mesh(new THREE.BoxGeometry(.085, .065, .25), mShoe), crank = new THREE.Mesh(new THREE.CylinderGeometry(.012, .012, 1, 6), mDark);
    [thigh, shin, knee, shoe, crank].forEach(m => g.add(m));
    return { s, thigh, shin, knee, shoe, crank, hip: V(s * .1, .99, -.17) };
  });
  g.scale.setScalar(ch.size || 1);
  return { g, legs, ch };
}
const _k = new THREE.Vector3(), _f = new THREE.Vector3(), _bb = new THREE.Vector3(), _fc = new THREE.Vector3();
function poseRider(R, phase) {
  const l1 = .45, l2 = .45;
  R.legs.forEach((lg, i) => {
    const th = phase + i * Math.PI;
    _f.set(lg.s * .12, .3 + Math.cos(th) * .17, .03 + Math.sin(th) * .17); // вперёд: верх → перед → низ → зад
    const dy = _f.y - lg.hip.y, dz = _f.z - lg.hip.z; let d = Math.hypot(dy, dz); d = Math.min(d, l1 + l2 - .005);
    const a = d / 2, hgt = Math.sqrt(Math.max(0, l1 * l1 - a * a)), uy = dy / d, uz = dz / d;
    _k.set(lg.s * .11, lg.hip.y + uy * a + uz * hgt, lg.hip.z + uz * a - uy * hgt);
    placeSeg(lg.thigh, lg.hip, _k); placeSeg(lg.shin, _k, _f); lg.knee.position.copy(_k);
    lg.shoe.position.set(_f.x, _f.y + .01, _f.z + .03); lg.shoe.rotation.x = -.15 + Math.sin(th) * .1;
    placeSeg(lg.crank, _bb.set(lg.s * .08, .3, .03), _fc.set(lg.s * .08, _f.y, _f.z));
  });
}
