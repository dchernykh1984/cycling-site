'use strict';
/* A building as OpenStreetMap outlines it (lm.outline, [[latitude, longitude], ...]), lm.h metres tall, its facade
   lm.c ("#rrggbb") with the windows every building of the scene has, a flat roof, and its name lit on the roof
   (lm.sign), turned to the route. Or one of parts, as OpenStreetMap's building:part draws it (lm.parts, [{outline, h,
   c, roof}]): each its own outline, height, walls' and roof's colours -- the Almaty Museum of Arts' limestone and
   aluminium blocks, 3 to 12 m, and its glass roof. */
addObject('building', (G, lm, T, { sink }) => {
  const pos = [], col = [], c = new THREE.Color(), base = -2 - sink;
  const push = (x, y, z) => { pos.push(x, y, z); col.push(c.r, c.g, c.b); };
  const block = (outline, top, walls, roof) => {
    let ring = outline.map(p => { const q = proj(p[0], p[1], T.origin); return [q.x - lm.x, q.z - lm.z]; });
    if (ring.length > 2 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1]) ring.pop();
    let area = 0; ring.forEach((p, i) => { const q = ring[(i + 1) % ring.length]; area += p[0] * q[1] - q[0] * p[1]; });
    if (area > 0) ring = ring.reverse(); // the way round that turns the walls' faces outwards, as js/osm.js draws them
    c.set(walls);
    ring.forEach((p, i) => {
      const q = ring[(i + 1) % ring.length];
      push(p[0], base, p[1]); push(q[0], base, q[1]); push(q[0], top, q[1]);
      push(p[0], base, p[1]); push(q[0], top, q[1]); push(p[0], top, p[1]);
    });
    c.set(roof || walls);
    THREE.ShapeUtils.triangulateShape(ring.map(p => new THREE.Vector2(p[0], p[1])), []).forEach(t => t.slice().reverse().forEach(k => push(ring[k][0], top, ring[k][1])));
    return ring;
  };
  const ring = lm.parts ? lm.parts.map(p => block(p.outline, p.h, p.c, p.roof)).flat() : block(lm.outline, lm.h, lm.c || '#d9d4c8');
  const top = lm.parts ? Math.max(...lm.parts.map(p => p.h)) : lm.h;
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3)); g.computeVertexNormals();
  G.add(new THREE.Mesh(g, osmMat));
  if (!lm.sign) return;
  // the name, white on a dark board on the roof, turned to the nearest of the route
  const cv = document.createElement('canvas'), x2 = cv.getContext('2d'); cv.width = 1024; cv.height = 192;
  x2.fillStyle = '#1d2329'; x2.fillRect(0, 0, cv.width, cv.height);
  x2.fillStyle = '#fff'; x2.font = '600 120px Golos Text, sans-serif'; x2.textAlign = 'center'; x2.textBaseline = 'middle'; x2.fillText(lm.sign, cv.width / 2, cv.height / 2 + 6);
  const tex = new THREE.CanvasTexture(cv), board = new THREE.Mesh(new THREE.BoxGeometry(32, 6, .6), [0, 1, 2, 3].map(() => new THREE.MeshLambertMaterial({ color: 0x1d2329 })).concat([new THREE.MeshBasicMaterial({ map: tex }), new THREE.MeshBasicMaterial({ map: tex })]));
  // over the outline's corner nearest the route, eight metres in from it
  const o = sampleAt(T, routeNearest(T, lm.x, lm.z).s, {}), rx = o.x - lm.x, rz = o.z - lm.z;
  const [ex, ez] = ring.reduce((a, p) => Math.hypot(p[0] - rx, p[1] - rz) < Math.hypot(a[0] - rx, a[1] - rz) ? p : a), l = Math.hypot(ex, ez) || 1;
  board.position.set(ex - ex / l * 8, top + 4, ez - ez / l * 8); board.rotation.y = Math.atan2(rx - board.position.x, rz - board.position.z); G.add(board);
});
