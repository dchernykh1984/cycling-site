/* An event's route track on its map (calendar_app.tracks): a quiet line in the skin's colours that
   the start marker stays above, arrows along it for the way it goes, and a view that opens on the
   whole track and the start. The arrows keep one distance apart on screen, so they are drawn again
   after every move: only where the map shows, never more than MAX_ARROWS at a time. */
(function () {
  'use strict';

  var SPACING = 90; // px along the line from one arrow to the next
  var HALF = 5; // px from an arrow's middle to its tip, and from the line to each wing
  var MAX_ARROWS = 60;

  function chevron(map, at, ux, uy) {
    // ux, uy: the unit vector the line runs along here, in screen px.
    return [
      L.point(at.x - ux * HALF - uy * HALF, at.y - uy * HALF + ux * HALF),
      L.point(at.x + ux * HALF, at.y + uy * HALF),
      L.point(at.x - ux * HALF + uy * HALF, at.y - uy * HALF - ux * HALF),
    ].map(function (point) { return map.layerPointToLatLng(point); });
  }

  function arrowsAlong(map, latlngs, view, marks) {
    var next = SPACING / 2;
    var run = 0;
    var from = map.latLngToLayerPoint(latlngs[0]);
    for (var i = 1; i < latlngs.length && marks.length < MAX_ARROWS; i++) {
      var to = map.latLngToLayerPoint(latlngs[i]);
      var length = from.distanceTo(to);
      while (length > 0 && run + length >= next && marks.length < MAX_ARROWS) {
        var share = (next - run) / length;
        var at = L.point(from.x + (to.x - from.x) * share, from.y + (to.y - from.y) * share);
        if (view.contains(at)) {
          marks.push(chevron(map, at, (to.x - from.x) / length, (to.y - from.y) / length));
        }
        next += SPACING;
      }
      run += length;
      from = to;
    }
  }

  function options(className, weight) {
    return { className: className, weight: weight, opacity: 1, interactive: false, lineCap: 'round', lineJoin: 'round' };
  }

  // geometry: a GeoJSON MultiLineString; start: the event's start point, or null when it has none of its own.
  window.drawRouteTrack = function (map, geometry, start) {
    L.geoJSON(geometry, { style: options('route-track-halo', 7) }).addTo(map);
    var track = L.geoJSON(geometry, { style: options('route-track', 4) }).addTo(map);
    var lines = geometry.coordinates.map(function (line) {
      return line.map(function (position) { return L.latLng(position[1], position[0]); });
    });
    var arrows = L.layerGroup().addTo(map);

    function drawArrows() {
      var size = map.getSize();
      var view = L.bounds(
        map.containerPointToLayerPoint([-HALF, -HALF]),
        map.containerPointToLayerPoint([size.x + HALF, size.y + HALF])
      );
      var marks = [];
      lines.forEach(function (latlngs) { arrowsAlong(map, latlngs, view, marks); });
      arrows.clearLayers();
      marks.forEach(function (mark) {
        arrows.addLayer(L.polyline(mark, options('route-track-halo', 6)));
        arrows.addLayer(L.polyline(mark, options('route-track-arrow', 3)));
      });
    }

    var bounds = track.getBounds();
    if (start) bounds.extend(start);
    // The marker stands 41 px above its point: room for it when the start is the northern edge.
    map.fitBounds(bounds, { paddingTopLeft: [24, 48], paddingBottomRight: [24, 24], maxZoom: 16 });
    map.on('moveend', drawArrows);
    drawArrows();
  };
})();
