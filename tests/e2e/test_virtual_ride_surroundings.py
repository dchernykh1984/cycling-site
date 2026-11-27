"""What stands round a virtual ride's route (js/surroundings.js) and the rider's line through its corners: the
roads it meets lie under its own road where they cross it, a bridge over it clears it and stands beside it, a
tunnel's roof clears the road under it, a dual carriageway's barrier stands between its halves, power lines stand
off the road and hang high over it, and a rider on a route that carries its line rides it within the road."""

import pytest
from playwright.sync_api import Page

# Every route the maps carry, its scene built once (a browser without 3D builds it all the same), and what a check
# finds wrong in it: `check` is the body of a function of (r, T, W, kids, out), out a list of faults to push to.
SCENES = """(check) => {
  if (!scene) {
    scene = new THREE.Scene(); renderer = { capabilities: { getMaxAnisotropy: () => 1 } }; makeMaterials();
  }
  const f = new Function('r', 'T', 'W', 'kids', 'out', check);
  return ROUTES.flatMap(r => {
    const w = buildWorld(r), out = [];
    f(r, w.T, r.width, scenery.children, out);
    return out;
  });
}"""


def _faults(page: Page, live_server, check: str) -> list[str]:
    """What the check finds wrong on every route; the check marks a route it found something to check on with
    "seen:", and some route has to be one -- a check that finds nothing anywhere checks nothing."""
    page.goto(f"{live_server.url}/static/trainer/alatau.html?lang=en")
    page.wait_for_function("typeof ROUTES !== 'undefined' && typeof buildWorld === 'function'")
    found = page.evaluate(SCENES, check)
    assert any(line.startswith("seen:") for line in found), "no route has what this checks"
    return [line for line in found if not line.startswith("seen:")]


@pytest.mark.django_db(transaction=True)
def test_a_rider_rides_the_route_s_line_through_its_corners_and_stays_on_its_road(page: Page, live_server):
    faults = _faults(
        page,
        live_server,
        """
        const lined = r.pts.every(p => p.length > 3), o = {}, keep = keepLane(W);
        if (lined) out.push('seen:' + r.id);
        world = buildCourse(r); // laneOf reads the course being ridden
        for (let s = 0; s < T.L; s += 5) {
          sampleAt(T, s, o);
          // the lanes riders keep: the right one, a bunch's narrowest and widest
          for (const lane of [keep, .8, W / 2 - 1]) {
            const at = laneOf({ lane }, o);
            if (Math.abs(at) > W / 2 - .6 + 1e-6) {
              out.push(r.id + ': off the road at ' + Math.round(s) + ' m'); return;
            }
          }
          // the rider keeping the right lane rides the route's own line where it has one
          const line = lined ? clamp(o.line, -W / 2 + .6, W / 2 - .6) : null;
          if (lined && Math.abs(laneOf({ lane: keep }, o) - line) > 1e-6) {
            out.push(r.id + ': off its line at ' + Math.round(s) + ' m'); return;
          }
          if (!lined && laneOf({ lane: keep }, o) !== keep) {
            out.push(r.id + ': a lane moved without a line'); return;
          }
        }
        """,
    )
    assert not faults, faults


@pytest.mark.django_db(transaction=True)
def test_a_road_the_route_meets_lies_under_its_road_where_they_cross(page: Page, live_server):
    faults = _faults(
        page,
        live_server,
        """
        const roads = kids.find(o => o.name === 'roads');
        if (!roads) return;
        out.push('seen:' + r.id);
        const p = roads.geometry.attributes.position;
        for (let i = 0; i < p.count; i++) {
          const n = routeNearest(T, p.getX(i), p.getZ(i)), up = p.getY(i) - n.y;
          // 4.5 m up and more: a road onto a bridge over the route, its end over the road's edge, clear of a rider
          // as the bridge's deck is; the valley drawn on past a finish (past T.L) is no road a rider rides
          if (n.d < W / 2 - .2 && n.s <= T.L && overTunnel(T, n.s) == null && up > .05 && up < 4.5) {
            out.push(r.id + ': a road ' + up.toFixed(2) + ' m over the route at ' + Math.round(n.s) + ' m');
            return;
          }
        }
        """,
    )
    assert not faults, faults


@pytest.mark.django_db(transaction=True)
def test_the_roads_round_the_route_lie_on_the_land_not_under_it(page: Page, live_server):
    # a stretch between two points of a road crossed a fold of the land drawn -- its planes tens of metres wide --
    # and went under it, by up to 6 m on Medeu's slopes; a road beside a tunnel's ramp or by the valley drawn on past
    # Medeu's finish was pulled down to them. Inside every triangle of the roads' mesh: at most half a metre under,
    # at one point in a hundred
    faults = _faults(
        page,
        live_server,
        """
        const land = kids.find(m => m.isMesh && m.geometry.type === 'PlaneGeometry' && m.material.vertexColors);
        const roads = kids.find(m => m.isMesh && m.name === 'roads');
        if (!roads) return;
        out.push('seen:' + r.id);
        const g = land.geometry; g.computeBoundingBox();
        const b = g.boundingBox, drawn = groundOf(g.attributes.position, b.min.x, b.min.z, b.max.x, b.max.z,
          g.parameters.widthSegments, g.parameters.heightSegments);
        const p = roads.geometry.attributes.position, idx = roads.geometry.index.array;
        let all = 0, under = 0, worst = 0;
        for (let t = 0; t < idx.length; t += 3) {
          for (const [u, v] of [[.33, .33], [.6, .2], [.2, .6]]) {
            const w = 1 - u - v, at = k => [p.getX(idx[t + k]), p.getY(idx[t + k]), p.getZ(idx[t + k])];
            const [a, c, d] = [at(0), at(1), at(2)];
            const mix = j => a[j] * w + c[j] * u + d[j] * v, x = mix(0), y = mix(1), z = mix(2);
            if (x <= b.min.x || x >= b.max.x || z <= b.min.z || z >= b.max.z) continue;
            all++;
            const deep = drawn(x, z) - y;
            if (deep > .02) { under++; worst = Math.max(worst, deep); }
          }
        }
        if (worst > .6 || under > all / 100) {
          out.push(r.id + ': ' + under + ' of ' + all + ', down to ' + worst.toFixed(2) + ' m');
        }
        """,
    )
    assert not faults, faults


@pytest.mark.django_db(transaction=True)
def test_a_bridge_over_the_route_clears_its_road_and_stands_beside_it(page: Page, live_server):
    faults = _faults(
        page,
        live_server,
        """
        const deck = kids.find(o => o.name === 'overpasses'), piers = kids.find(o => o.name === 'piers');
        if (!deck) return;
        out.push('seen:' + r.id);
        const p = deck.geometry.attributes.position;
        for (let i = 0; i < p.count; i++) {
          const n = routeNearest(T, p.getX(i), p.getZ(i));
          if (n.d < W / 2 && p.getY(i) - n.y < 4.5) {
            out.push(r.id + ': a bridge ' + (p.getY(i) - n.y).toFixed(1) + ' m over the road'); return;
          }
        }
        const m = new THREE.Matrix4(), v = new THREE.Vector3();
        for (let i = 0; i < (piers ? piers.count : 0); i++) {
          piers.getMatrixAt(i, m); v.setFromMatrixPosition(m);
          const d = routeGap(T, v.x, v.z);
          if (d < W / 2 + .5) { out.push(r.id + ': a pier ' + d.toFixed(1) + ' m from the route'); return; }
        }
        """,
    )
    assert not faults, faults


@pytest.mark.django_db(transaction=True)
def test_the_road_onto_a_bridge_over_the_route_climbs_onto_its_deck(page: Page, live_server):
    # OpenStreetMap draws a bridge apart from the roads that lead to it: at each end of a road bridge's deck the road
    # touching it stands at the deck's height, its ramp going down from there -- not on the ground under the deck
    faults = _faults(
        page,
        live_server,
        """
        const decks = overDecks(T, W, r.over || []).filter(d => !d.b.foot);
        if (!decks.length) return;
        out.push('seen:' + r.id);
        const roads = kids.find(m => m.name === 'roads'), p = roads.geometry.attributes.position;
        for (const d of decks) for (const e of [d.q[0], d.q[d.q.length - 1]]) {
          let on = false, near = false;
          for (let i = 0; i < p.count; i++) {
            if (Math.hypot(p.getX(i) - e.x, p.getZ(i) - e.z) > 8) continue;
            near = true;
            if (Math.abs(p.getY(i) - d.deck) < .3) on = true;
          }
          if (near && !on) { out.push(r.id + ': a road meets its bridge under the deck'); return; }
        }
        """,
    )
    assert not faults, faults


# A made-up route north, 1 km on the flat, with road bridges across it and roads round them, given in metres east
# and north of its start; what it answers is, for each place asked about, how far the road nearest a bridge's deck
# stands from the deck's height there.
_BRIDGES = """({ over, roads, ends }) => {
  if (!scene) {
    scene = new THREE.Scene(); renderer = { capabilities: { getMaxAnisotropy: () => 1 } }; makeMaterials();
  }
  const named = { ru: 'n', kk: 'n', en: 'n' }, lat0 = 43.2, lon0 = 76.9;
  const at = ([east, north]) => [lat0 + north / 111195, lon0 + east / (111320 * Math.cos(lat0 * Math.PI / 180))];
  const route = { id: 'bridges-test', name: named, desc: named, loop: false, width: 10, lanes: 2, scenery: 'city',
    pts: [[...at([0, 0]), 800], [...at([0, 500]), 800], [...at([0, 1000]), 800]],
    over: over.map(pts => ({ w: 8, pts: pts.map(at) })), roads: roads.map(pts => ({ w: 6, pts: pts.map(at) })) };
  addMap({ id: 'bridges-test', name: named, origin: { lat: lat0, lon: lon0 }, routes: [route] });
  const T = buildWorld(ROUTES.find(r => r.id === 'bridges-test')).T;
  const deck = overDecks(T, route.width, route.over)[0].deck;
  const p = scenery.children.find(m => m.name === 'roads').geometry.attributes.position;
  return ends.map(e => {
    const q = xzOf(T, at(e));
    let gap = Infinity;
    for (let i = 0; i < p.count; i++) {
      if (Math.hypot(p.getX(i) - q.x, p.getZ(i) - q.z) < 5) gap = Math.min(gap, Math.abs(p.getY(i) - deck));
    }
    return gap;
  });
}"""


def _bridges(page: Page, live_server, **made) -> list[float]:
    page.goto(f"{live_server.url}/static/trainer/alatau.html?lang=en")
    page.wait_for_function("typeof ROUTES !== 'undefined' && typeof buildWorld === 'function'")
    return page.evaluate(_BRIDGES, made)


@pytest.mark.django_db(transaction=True)
def test_a_slip_road_from_a_bridge_s_end_into_the_route_starts_at_the_deck_s_height(page: Page, live_server):
    # from the bridge's end, 12 m off the route's middle, a slip road runs on 200 m into the route: only its last
    # metres come down to the route, not its start by the deck
    gaps = _bridges(
        page, live_server, over=[[[-12, 300], [12, 300]]], roads=[[[12, 300], [40, 380], [6, 500]]], ends=[[12, 300]]
    )
    assert gaps[0] < 0.3, gaps


@pytest.mark.django_db(transaction=True)
def test_a_road_between_two_bridges_meets_each_at_its_deck(page: Page, live_server):
    # two bridges 40 m apart and a road between their ends: it takes the ramp of each, not only of the first it met
    gaps = _bridges(
        page,
        live_server,
        over=[[[-12, 300], [12, 300]], [[-12, 340], [12, 340]]],
        roads=[[[12, 300], [12, 340]]],
        ends=[[12, 300], [12, 340]],
    )
    assert max(gaps) < 0.3, gaps


@pytest.mark.django_db(transaction=True)
def test_the_ground_keeps_under_the_road_and_its_sides(page: Page, live_server):
    # between the ground's vertices, tens of metres apart, the drawn ground is a plane: one leaning on Medeu's gorge
    # wall rose over its road by up to 4 m. Outside a tunnel's cutting, it lies 10 cm under the road and a gorge's
    # gravel beside it, every 2 m along the route and every metre across
    faults = _faults(
        page,
        live_server,
        """
        const land = kids.find(m => m.isMesh && m.geometry.type === 'PlaneGeometry' && m.material.vertexColors);
        const g = land.geometry; g.computeBoundingBox();
        const b = g.boundingBox, drawn = groundOf(g.attributes.position, b.min.x, b.min.z, b.max.x, b.max.z,
          g.parameters.widthSegments, g.parameters.heightSegments), o = {}, wide = W + (r.scenery === 'gorge' ? 5 : 0);
        if (r.scenery === 'gorge') out.push('seen:' + r.id);
        for (let s = 0; s < T.L; s += 2) {
          if (r.tunnels && cutGround(T, s) != null) continue;
          sampleAt(T, s, o);
          for (let off = -wide / 2; off <= wide / 2; off += 1) {
            const over = drawn(o.x + o.rx * off, o.z + o.rz * off) - o.y;
            if (over > -.09) {
              const cm = Math.round(Math.abs(over) * 100), where = over > 0 ? ' cm over' : ' cm under';
              out.push(r.id + ': the ground ' + cm + where + ' the road at ' + Math.round(s) + ' m');
              return;
            }
          }
        }
        """,
    )
    assert not faults, faults


@pytest.mark.django_db(transaction=True)
def test_a_tunnel_s_roof_clears_the_road_under_it_and_the_land_keeps_its_level_beside_it(page: Page, live_server):
    faults = _faults(
        page,
        live_server,
        """
        const zones = tunnelZones(T), o = {};
        if (!zones.length) return;
        out.push('seen:' + r.id);
        for (const z of zones) {
          const mid = (z.p0 + z.p1) / 2;
          sampleAt(T, mid, o);
          // the road down in the cutting, the land beside it at the ground line
          const beside = terrainH(T, o.x + o.rx * (W / 2 + 40), o.z + o.rz * (W / 2 + 40));
          if (beside - o.y < 4) {
            out.push(r.id + ': the land beside its tunnel ' + (beside - o.y).toFixed(1) + ' m over the road');
          }
        }
        const roof = kids.find(m => m.name === 'structures'), p = roof.geometry.attributes.position;
        for (let i = 0; i < p.count; i++) {
          const n = routeNearest(T, p.getX(i), p.getZ(i));
          if (n.d < W / 2 - .5 && overTunnel(T, n.s) != null && p.getY(i) - n.y < 4.5) {
            out.push(r.id + ': a tunnel ' + (p.getY(i) - n.y).toFixed(1) + ' m high'); return;
          }
        }
        """,
    )
    assert not faults, faults


@pytest.mark.django_db(transaction=True)
def test_a_rider_riding_up_to_a_tunnel_sees_its_portal_not_the_street_through_its_roof(page: Page, live_server):
    # the roof was two sheets a metre apart: riding up to it, a bridge drawn as two thin lines with the street beyond
    # showing between them (Granfondo 2026's first, under Al-Farabi)
    faults = _faults(
        page,
        live_server,
        """
        const zones = tunnelZones(T), o = {}, ray = new THREE.Raycaster();
        if (!zones.length) return;
        out.push('seen:' + r.id);
        const roof = kids.find(m => m.name === 'structures');
        for (const z of zones) {
          // from the road's line 15 m before the portal, level with the middle of the roof's thickness
          sampleAt(T, z.p0, o);
          const face = new THREE.Vector3(o.x, cutGround(T, z.p0) - .5, o.z);
          sampleAt(T, z.p0 - 15, o);
          const eye = new THREE.Vector3(o.x, face.y, o.z), d = face.clone().sub(eye);
          ray.set(eye, d.clone().normalize()); ray.far = d.length() + 1;
          if (!ray.intersectObject(roof).length) out.push(r.id + ': a roof at ' + Math.round(z.p0) + ' m, see-through');
        }
        """,
    )
    assert not faults, faults


@pytest.mark.django_db(transaction=True)
def test_the_land_is_left_out_of_a_tunnel_and_its_cutting_from_wall_to_wall(page: Page, live_server):
    # the land is drawn in cells 40 m across: over a tunnel and its cutting it would span the road like a lid and cut
    # through the tunnel (Granfondo 2026's, the centre's under Al-Farabi), so its shader leaves it out in boxes along
    # the road -- each point of the road down there, from wall to wall, in one of them and under its top
    faults = _faults(
        page,
        live_server,
        """
        const zones = tunnelZones(T), o = {};
        if (!zones.length) return;
        out.push('seen:' + r.id);
        const land = kids.find(m => m.isMesh && m.geometry.type === 'PlaneGeometry' && m.material.vertexColors);
        if (!land.material.onBeforeCompile) { out.push(r.id + ': its land leaves nothing out'); return; }
        const holes = holesOf(T, W);
        for (const z of zones) for (let s = z.s0; s <= z.s1; s += 2) {
          sampleAt(T, s, o);
          for (const k of [-1, 0, 1]) {
            const x = o.x + o.rx * k * W / 2, y = terrainH(T, x, o.z + o.rz * k * W / 2), zz = o.z + o.rz * k * W / 2;
            const lid = holes.every(([a, b]) => {
              const dx = x - a.x, dz = zz - a.y, u = dx * a.z + dz * a.w, v = dz * a.z - dx * a.w;
              const top = b.z + (b.w - b.z) * Math.min(1, Math.max(0, u / (2 * b.x) + .5)) + 1.5;
              return Math.abs(u) >= b.x || Math.abs(v) >= b.y || y >= top;
            });
            if (lid) { out.push(r.id + ': the land over its road at ' + Math.round(s) + ' m'); return; }
          }
        }
        """,
    )
    assert not faults, faults


@pytest.mark.django_db(transaction=True)
def test_a_barrier_between_a_dual_carriageway_s_halves_stands_off_both(page: Page, live_server):
    faults = _faults(
        page,
        live_server,
        """
        const median = kids.find(o => o.name === 'median');
        if (!median) return;
        out.push('seen:' + r.id);
        const p = median.geometry.attributes.position;
        for (let i = 0; i < p.count; i++) {
          const d = routeGap(T, p.getX(i), p.getZ(i));
          if (d < W / 2 - .3) {
            out.push(r.id + ': a barrier ' + d.toFixed(1) + ' m from a stretch of the route'); return;
          }
        }
        """,
    )
    assert not faults, faults


@pytest.mark.django_db(transaction=True)
def test_power_lines_stand_off_the_road_and_hang_high_over_it(page: Page, live_server):
    faults = _faults(
        page,
        live_server,
        """
        const m = new THREE.Matrix4(), v = new THREE.Vector3();
        for (const name of ['towers', 'poles']) {
          const im = kids.find(o => o.name === name);
          for (let i = 0; i < (im ? im.count : 0); i++) {
            im.getMatrixAt(i, m); v.setFromMatrixPosition(m);
            if (routeGap(T, v.x, v.z) < W / 2 + 3) {
              out.push(r.id + ': a ' + name.slice(0, -1) + ' on the road'); return;
            }
          }
        }
        const wires = kids.find(o => o.name === 'wires');
        if (!wires) return;
        out.push('seen:' + r.id);
        const p = wires.geometry.attributes.position;
        for (let i = 0; i < p.count; i++) {
          const n = routeNearest(T, p.getX(i), p.getZ(i));
          if (n.d < W / 2 && p.getY(i) - n.y < 5) {
            out.push(r.id + ': a wire ' + (p.getY(i) - n.y).toFixed(1) + ' m over the road'); return;
          }
        }
        """,
    )
    assert not faults, faults
