'use strict';
/* A sign by the road: lm.text as the place writes it, lm.ink on a board of lm.c, lm.w metres wide (from the text when
   not given), on two posts with its lower edge lm.up metres over the ground (2.2 unless given) -- its face turned to
   the riders coming up to it on the route's way there, SIGN_FACE_M before it. */
const SIGN_FACE_M = 30, SIGN_BOARD_H = 1.3;
addObject('sign', (G, lm, T, { lam, box, cyl }) => {
  const text = lm.text, up = lm.up != null ? lm.up : 2.2, w = lm.w || Math.max(3, text.length * .62), h = lm.board || SIGN_BOARD_H;
  const tex = canvasTex(1024, Math.round(1024 * h / w), (c, cw, ch) => {
    c.fillStyle = lm.c || '#1f4e8c'; c.fillRect(0, 0, cw, ch);
    c.strokeStyle = lm.ink || '#ffffff'; c.lineWidth = ch * .06; c.strokeRect(c.lineWidth, c.lineWidth, cw - 2 * c.lineWidth, ch - 2 * c.lineWidth);
    c.fillStyle = lm.ink || '#ffffff'; c.textAlign = 'center'; c.textBaseline = 'middle';
    let size = ch * .62; c.font = '700 ' + size + 'px Golos Text, sans-serif';
    while (c.measureText(text).width > cw * .9 && size > 8) { size *= .92; c.font = '700 ' + size + 'px Golos Text, sans-serif'; }
    c.fillText(text, cw / 2, ch / 2 + size * .04);
  });
  const edge = lam(lm.c || 0x1f4e8c), face = new THREE.MeshBasicMaterial({ map: tex });
  const board = new THREE.Mesh(new THREE.BoxGeometry(w, h, .12), [edge, edge, edge, edge, face, edge]);
  board.position.y = up + h / 2; G.add(board);
  [-1, 1].forEach(k => cyl(.07, .07, up + h, 0x8d9296, k * (w / 2 - .25), 0, -.1, 8));
  // turned to the riders coming to it: its face towards the route SIGN_FACE_M back along the way there
  const o = sampleAt(T, Math.max(0, lm.s - SIGN_FACE_M), {});
  G.rotation.y = Math.atan2(o.x - lm.x, o.z - lm.z);
});
